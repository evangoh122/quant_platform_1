"""
notebooks/refresh_bronze_options.py
Bronze options refresh — lane `options`.

Refreshes two independent Bronze sources (append-only, no UPDATE/DELETE/
OVERWRITE/replaceWhere/MERGE-update):

  1. Daily option aggregates
       source : us_options_opra/day_aggs_v1  (Massive flat files, S3)
       target : bootcamp_students.evangoh_capstone.bronze_options_day
       key    : (contract_symbol, event_ts, timespan)

  2. IV/Greeks chain snapshots
       source : Polygon REST `list_snapshot_options_chain` (current snapshot)
       target : bootcamp_students.evangoh_capstone.bronze_options_quotes
       key    : (option_symbol, participant_ts)

The existing Polygon REST endpoint is a *current* snapshot, not a historical
snapshot API. This lane therefore appends only the snapshot the provider
actually returns and never fabricates historical daily snapshots.

Safety rules honoured here:
  - Append-only writes. The only UPDATE is the operational ingestion log
    (massive_ingestion_log), which is metadata, not a Bronze history table.
  - Incoming batches are deduplicated with dropDuplicates(key_columns) and then
    left-anti-joined against the target's projected keys before append.
  - Every SQL value is passed via parameter markers (`spark.sql(..., args=...)`)
    or the DataFrame API; no f-string SQL filters.
  - No secret values are ever printed.

Run modes (mutually exclusive):
    python notebooks/refresh_bronze_options.py --dry-run [--start-date ...] [--end-date ...]
    python notebooks/refresh_bronze_options.py --write    [--start-date ...] [--end-date ...]
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
CATALOG = "bootcamp_students"
SCHEMA = "evangoh_capstone"
CATALOG_SCHEMA = f"{CATALOG}.{SCHEMA}"

DAY_PREFIX = "us_options_opra/day_aggs_v1"
DAY_DATASET = DAY_PREFIX
DAY_TABLE = f"{CATALOG_SCHEMA}.bronze_options_day"
QUOTES_TABLE = f"{CATALOG_SCHEMA}.bronze_options_quotes"
INGEST_LOG_TABLE = f"{CATALOG_SCHEMA}.massive_ingestion_log"

BUCKET = "flatfiles"
ENDPOINT_CANDIDATES = ["files.massive.com", "files.polygon.io"]

VOLUME_NAME = "flatfiles_raw"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}"

SECRET_SCOPE = "evangoh_capstone"
MASSIVE_ACCESS_KEY_NAME = "massive_s3_access_key"
MASSIVE_SECRET_KEY_NAME = "massive_s3_secret_key"
POLYGON_KEY_NAME = "polygon_api_key"

END_DATE_DEFAULT = "2026-10-03"

# Streaming batch size for driver-side CSV parsing (row dicts per flush).
BATCH_SIZE = 50_000

# Natural keys.
DAY_KEY_COLUMNS = ["contract_symbol", "event_ts", "timespan"]
SNAPSHOT_KEY_COLUMNS = ["option_symbol", "participant_ts"]

# Daily aggregate target column order (matches live table).
DAY_TARGET_COLUMNS = [
    "contract_symbol", "underlying", "expiry", "strike", "right",
    "event_ts", "event_date", "event_year",
    "open", "high", "low", "close", "volume", "trade_count",
    "timespan", "source", "source_file", "ingest_ts",
]

# Snapshot target column order (matches live bronze_options_quotes).
QUOTES_TARGET_COLUMNS = [
    "option_symbol", "underlying", "expiry", "strike", "right",
    "bid", "ask", "bid_size", "ask_size", "midpoint",
    "participant_ts", "sequence_id", "source", "raw_payload", "ingest_ts",
    "last_price", "volume", "open_interest", "implied_volatility",
    "delta", "gamma", "theta", "vega",
]

# Universe used for the current-snapshot chain retrieval (matches the archived
# Polygon snapshot universe in notebooks/01_ingest_market_data.py).
SNAPSHOT_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA",
    "AMD", "AVGO", "QCOM", "INTC", "MU",
    "SPY", "QQQ", "IWM",
    "XLK", "XLF", "XLE",
    "VIXY", "JPM",
]

SNAPSHOT_PAGE_LIMIT = 250

# OPRA option symbol: O:AAPL250117C00200000 -> AAPL / 250117 / C / 200.000
OPRA_REGEX = re.compile(r"^O:(.+?)(\d{6})([CP])(\d{8})$")

_FORBIDDEN_CODES = ("403", "AccessDenied", "Forbidden")


# -----------------------------------------------------------------------------
# Pure helpers (import-safe, no Spark / no secrets)
# -----------------------------------------------------------------------------

def parse_date(value):
    """Parse YYYY-MM-DD into a datetime.date. Raises ValueError if malformed."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_window(start_date, end_date):
    """Inclusive list of ISO date strings from start_date through end_date."""
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError(f"END_DATE ({end_date}) is before START_DATE ({start_date})")
    out = []
    d = start
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# NYSE market holidays (fixed + observed) for 2025-2026.
_NYSE_HOLIDAYS = frozenset([
    # 2025
    date(2025, 1, 1),   # New Year's Day
    date(2025, 1, 20),  # MLK Jr Day
    date(2025, 2, 17),  # Presidents Day
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 26),  # Memorial Day
    date(2025, 6, 19),  # Juneteenth
    date(2025, 7, 4),   # Independence Day
    date(2025, 9, 1),   # Labor Day
    date(2025, 11, 27), # Thanksgiving
    date(2025, 12, 25), # Christmas
    # 2026
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Jr Day
    date(2026, 2, 16),  # Presidents Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
])


def trading_days(start_date, end_date):
    """NYSE trading days (weekdays minus US market holidays) as ISO strings."""
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError(f"END_DATE ({end_date}) is before START_DATE ({start_date})")
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in _NYSE_HOLIDAYS:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def s3_key_for_date(date_str):
    """Massive object key for an options day aggregate file."""
    y, m, d = date_str.split("-")
    return f"{DAY_PREFIX}/{y}/{m}/{date_str}.csv.gz"


def parse_opra_symbol(ticker):
    """Parse an OPRA option symbol.

    Returns (underlying, expiry_date, right, strike) where right is
    ``CALL``/``PUT`` and strike is a float, or ``None`` when the symbol is
    malformed.
    """
    if not ticker:
        return None
    m = OPRA_REGEX.match(ticker)
    if not m:
        return None
    underlying = m.group(1)
    expiry_raw = m.group(2)
    right_raw = m.group(3)
    strike_raw = m.group(4)
    if not (underlying and expiry_raw and right_raw and strike_raw):
        return None
    try:
        expiry = datetime.strptime(expiry_raw, "%y%m%d").date()
        strike = int(strike_raw) / 1000.0
    except (ValueError, OverflowError):
        return None
    right = "CALL" if right_raw == "C" else "PUT"
    return underlying, expiry, right, strike


def ns_to_ts(value):
    """Convert a nanosecond epoch (Massive/Polygon) to aware UTC datetime."""
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000_000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def as_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def resolve_snapshot_ts(provider_ts, snapshot_ts):
    """Use the provider quote timestamp when present, else the shared run time.

    ``provider_ts`` and ``snapshot_ts`` are both datetimes; the result is the
    value that becomes ``participant_ts`` for the snapshot key.
    """
    return provider_ts if provider_ts is not None else snapshot_ts


def canonical_day_right(raw):
    """Canonicalise a raw day-agg ``right`` value to ``'PUT'`` or ``'CALL'``.

    Accepts every known encoding produced by ingestion writers:

    * ``'PUT'`` / ``'CALL'``  — ``refresh_bronze_options.py`` day-agg path
    * ``'P'``   / ``'C'``    — ``01_ingest_market_data.py`` Quick Start
    * ``'put'`` / ``'call'``  — ``refresh_bronze_options.py`` quotes path
      (only relevant if rows leak into the day table)

    Returns ``None`` for any unrecognised value.
    """
    val = (raw or "").upper()
    if val in ("PUT", "P"):
        return "PUT"
    if val in ("CALL", "C"):
        return "CALL"
    return None


def _right_from_contract_type(contract_type):
    """Normalise a Polygon ``contract_type`` (call/put) to 'call'/'put'.

    Quotes path (bronze_options_quotes) uses lowercase to match the existing
    live-table encoding.  The day-agg path (parse_opra_symbol / _shape_day)
    emits uppercase 'CALL'/'PUT' separately.
    """
    ctype = (contract_type or "").lower()
    if ctype in ("call", "c"):
        return "call"
    if ctype in ("put", "p"):
        return "put"
    return None


def shape_quote_row(snap, underlying, snapshot_ts, source="polygon"):
    """Map a Polygon ``OptionContractSnapshot`` to a bronze_options_quotes row.

    Populates the live table's columns, including Greeks when present. Uses the
    provider quote timestamp (SIP, then participant, then retrieval time) for
    ``participant_ts``. Returns ``None`` when there is no usable option symbol.
    """
    details = getattr(snap, "details", None)
    opt_sym = getattr(details, "ticker", None) if details else None
    if not opt_sym:
        return None

    expiry_raw = getattr(details, "expiration_date", None) if details else None
    if expiry_raw and isinstance(expiry_raw, str):
        try:
            expiry = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
        except ValueError:
            expiry = None
    else:
        expiry = expiry_raw
    strike = getattr(details, "strike_price", None) if details else None
    right = _right_from_contract_type(
        getattr(details, "contract_type", None) if details else None
    )

    last_q = getattr(snap, "last_quote", None)
    bid = getattr(last_q, "bid", None) if last_q else None
    ask = getattr(last_q, "ask", None) if last_q else None
    bid_sz = getattr(last_q, "bid_size", None) if last_q else None
    ask_sz = getattr(last_q, "ask_size", None) if last_q else None
    midpoint = getattr(last_q, "midpoint", None) if last_q else None
    if midpoint is None and bid is not None and ask is not None:
        midpoint = (bid + ask) / 2.0

    sip_ns = getattr(last_q, "sip_timestamp", None) if last_q else None
    part_ns = getattr(last_q, "participant_timestamp", None) if last_q else None
    provider_ts = ns_to_ts(sip_ns) or ns_to_ts(part_ns)
    participant_ts = resolve_snapshot_ts(provider_ts, snapshot_ts)

    greeks = getattr(snap, "greeks", None)
    last_t = getattr(snap, "last_trade", None)
    day = getattr(snap, "day", None)

    return {
        "option_symbol": opt_sym,
        "underlying": underlying,
        "expiry": expiry,
        "strike": float(strike) if strike is not None else None,
        "right": right,
        "bid": float(bid) if bid is not None else None,
        "ask": float(ask) if ask is not None else None,
        "bid_size": int(bid_sz) if bid_sz is not None else None,
        "ask_size": int(ask_sz) if ask_sz is not None else None,
        "midpoint": float(midpoint) if midpoint is not None else None,
        "participant_ts": participant_ts,
        "sequence_id": None,
        "source": source,
        "raw_payload": None,
        "ingest_ts": snapshot_ts,
        "last_price": float(getattr(last_t, "price", None))
        if last_t is not None and getattr(last_t, "price", None) is not None
        else None,
        "volume": int(getattr(day, "volume", None))
        if day is not None and getattr(day, "volume", None) is not None
        else None,
        "open_interest": float(getattr(snap, "open_interest", None))
        if getattr(snap, "open_interest", None) is not None
        else None,
        "implied_volatility": float(getattr(snap, "implied_volatility", None))
        if getattr(snap, "implied_volatility", None) is not None
        else None,
        "delta": float(getattr(greeks, "delta", None))
        if greeks is not None and getattr(greeks, "delta", None) is not None
        else None,
        "gamma": float(getattr(greeks, "gamma", None))
        if greeks is not None and getattr(greeks, "gamma", None) is not None
        else None,
        "theta": float(getattr(greeks, "theta", None))
        if greeks is not None and getattr(greeks, "theta", None) is not None
        else None,
        "vega": float(getattr(greeks, "vega", None))
        if greeks is not None and getattr(greeks, "vega", None) is not None
        else None,
    }


# -----------------------------------------------------------------------------
# Environment / secrets (lazy imports)
# -----------------------------------------------------------------------------

def _get_dbutils():
    return globals().get("dbutils")


def _get_spark():
    dbutils = _get_dbutils()
    if dbutils is not None:
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    from databricks.connect import DatabricksSession
    return DatabricksSession.builder.serverless(True).getOrCreate()


def _get_secret(key_name):
    dbutils = _get_dbutils()
    if dbutils is not None:
        return dbutils.secrets.get(scope=SECRET_SCOPE, key=key_name)
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE"))
    return w.secrets.get_secret(SECRET_SCOPE, key_name).value


def _load_secrets():
    """Return (access_key, secret_key, polygon_key). Never printed."""
    access_key = _get_secret(MASSIVE_ACCESS_KEY_NAME)
    secret_key = _get_secret(MASSIVE_SECRET_KEY_NAME)
    polygon_key = _get_secret(POLYGON_KEY_NAME)
    return access_key, secret_key, polygon_key


def _make_s3_client(host, access_key, secret_key):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=f"https://{host}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )


def _is_forbidden(exc):
    code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    return code in _FORBIDDEN_CODES or (code is not None and "403" in str(code))


def _detect_s3(access_key, secret_key, probe_prefix):
    """Probe both endpoints by listing the day prefix; return (client, host)
    or (None, None). A successful list (even empty) confirms the credentials
    and endpoint work, unlike a per-file HEAD which can 404 on weekends."""
    for host in ENDPOINT_CANDIDATES:
        client = _make_s3_client(host, access_key, secret_key)
        try:
            client.list_objects_v2(Bucket=BUCKET, Prefix=probe_prefix, MaxKeys=1)
            return client, host
        except Exception as exc:
            print(f"  [detect] {host}: {type(exc).__name__}: {exc}")
            continue
    return None, None


# -----------------------------------------------------------------------------
# Ingestion log (operational metadata; parameterized SQL only)
# -----------------------------------------------------------------------------

def already_ingested(spark, source_file, dataset):
    return spark.sql(
        "SELECT 1 FROM " + INGEST_LOG_TABLE +
        " WHERE source_file = :sf AND dataset = :ds AND status = 'SUCCESS' LIMIT 1",
        args={"sf": source_file, "ds": dataset},
    ).count() > 0


def log_start(spark, source_file, dataset):
    now = datetime.now(timezone.utc)
    spark.createDataFrame(
        [(source_file, dataset, "RUNNING", 0, now, None, None)],
        "source_file string, dataset string, status string, row_count long, "
        "started_at timestamp, completed_at timestamp, error_message string",
    ).write.format("delta").mode("append").saveAsTable(INGEST_LOG_TABLE)


def log_finish(spark, source_file, dataset, row_count, error_message=None):
    if error_message is None:
        spark.sql(
            "UPDATE " + INGEST_LOG_TABLE +
            " SET status = 'SUCCESS', row_count = :rc, "
            " completed_at = current_timestamp(), error_message = NULL "
            " WHERE source_file = :sf AND dataset = :ds AND status = 'RUNNING'",
            args={"rc": int(row_count), "sf": source_file, "ds": dataset},
        )
    else:
        spark.sql(
            "UPDATE " + INGEST_LOG_TABLE +
            " SET status = 'FAILED', row_count = :rc, "
            " completed_at = current_timestamp(), error_message = :err "
            " WHERE source_file = :sf AND dataset = :ds AND status = 'RUNNING'",
            args={
                "rc": int(row_count),
                "err": str(error_message)[:4000],
                "sf": source_file,
                "ds": dataset,
            },
        )


# -----------------------------------------------------------------------------
# Daily aggregate ingestion (append + anti-join)
# -----------------------------------------------------------------------------

def _shape_day(spark, vol_file, source_file, ingest_ts):
    """Read one staged options day CSV via Spark and shape it into the target
    columns (OPRA parsing + timestamp derivation). Rejects malformed contracts
    and null event timestamps.

    ``right`` is canonicalised via :func:`canonical_day_right` (the single
    source of truth for day-agg right encoding).
    """
    from pyspark.sql import functions as F
    from pyspark.sql.types import StringType

    _day_right_udf = F.udf(canonical_day_right, StringType())
    pattern = OPRA_REGEX.pattern
    raw = spark.read.option("header", True).csv(vol_file)
    event_ts = (
        F.col("window_start").cast("double") / F.lit(1_000_000_000.0)
    ).cast("timestamp")

    df = raw.select(
        F.col("ticker").alias("contract_symbol"),
        F.regexp_extract("ticker", pattern, 1).alias("underlying"),
        F.to_date(F.regexp_extract("ticker", pattern, 2), "yyMMdd").alias("expiry"),
        (F.regexp_extract("ticker", pattern, 4).cast("double") / F.lit(1000.0))
        .alias("strike"),
        _day_right_udf(F.regexp_extract("ticker", pattern, 3)).alias("right"),
        event_ts.alias("event_ts"),
        F.to_date(event_ts).alias("event_date"),
        F.year(event_ts).alias("event_year"),
        F.col("open").cast("double").alias("open"),
        F.col("high").cast("double").alias("high"),
        F.col("low").cast("double").alias("low"),
        F.col("close").cast("double").alias("close"),
        F.col("volume").cast("long").alias("volume"),
        F.col("transactions").cast("long").alias("trade_count"),
        F.lit("day").alias("timespan"),
        F.lit("massive_flatfile").alias("source"),
        F.lit(source_file).alias("source_file"),
        F.lit(ingest_ts).alias("ingest_ts"),
    )

    return df.filter(
        (F.col("underlying") != "")
        & (F.col("expiry").isNotNull())
        & (F.col("strike").isNotNull())
        & (F.col("right").isNotNull())
        & F.col("event_ts").isNotNull()
    )


def _in_databricks():
    """True when running inside a Databricks runtime (FUSE-mounted /Volumes)."""
    return bool(os.environ.get("DATABRICKS_RUNTIME_VERSION"))


def _stage_file(s3, key, sdk_client, local_root):
    """Download one Massive gzip CSV into the UC Volume and return its Volume
    path. Returns ``None`` when the object is 403 (outside entitlement)."""
    vol_path = f"{VOLUME_PATH}/{key}"
    try:
        if _in_databricks():
            # Databricks driver can write directly into the mounted Volume.
            os.makedirs(os.path.dirname(vol_path), exist_ok=True)
            s3.download_file(BUCKET, key, vol_path)
            return vol_path
        # Outside Databricks: stage locally, then upload via SDK Files API.
        local = os.path.join(local_root, key)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        s3.download_file(BUCKET, key, local)
        try:
            sdk_client.files.create_directory(os.path.dirname(vol_path))
        except Exception:
            pass  # directory already exists
        with open(local, "rb") as fh:
            sdk_client.files.upload(vol_path, fh, overwrite=True)
        os.remove(local)
        return vol_path
    except Exception as exc:
        if _is_forbidden(exc):
            return None
        raise


def _clear_staged(s3_key, sdk_client):
    vol_path = f"{VOLUME_PATH}/{s3_key}"
    if _in_databricks():
        try:
            os.remove(vol_path)
        except OSError:
            pass
    else:
        try:
            sdk_client.files.delete(vol_path)
        except Exception:
            pass


def _resolve_write_columns(spark, df, table):
    """Return *df* columns reordered to match the live *table* schema.

    Raises ``ValueError`` when the column sets differ (names).  This prevents
    silent data loss from the old behaviour that silently dropped columns the
    live table lacked.
    """
    try:
        table_cols = [
            r["col_name"]
            for r in spark.sql(f"DESCRIBE TABLE {table}").collect()
            if r["col_name"] and not r["col_name"].startswith("#")
        ]
    except Exception:
        return list(df.columns)

    df_set = set(df.columns)
    table_set = set(table_cols)

    missing_in_df = table_set - df_set
    extra_in_df = df_set - table_set

    if missing_in_df or extra_in_df:
        parts = []
        if missing_in_df:
            parts.append(f"missing from DataFrame: {sorted(missing_in_df)}")
        if extra_in_df:
            parts.append(f"extra in DataFrame: {sorted(extra_in_df)}")
        raise ValueError(
            f"Schema mismatch between DataFrame and table {table}: "
            + "; ".join(parts)
        )

    return [c for c in table_cols if c in df_set]


def _anti_join_new(spark, incoming_df, key_columns, table, date_col, start_date, end_date):
    """Drop duplicates on the incoming key and left-anti-join against the
    target's projected keys, pruned by date range."""
    from pyspark.sql import functions as F
    dedup = incoming_df.dropDuplicates(key_columns)
    target_keys = (
        spark.table(table)
        .filter(
            (F.col(date_col) >= F.lit(start_date).cast("date"))
            & (F.col(date_col) <= F.lit(end_date).cast("date"))
        )
        .select(key_columns)
        .distinct()
    )
    return dedup.join(target_keys, key_columns, "left_anti")


def _run_daily(spark, s3, s3_host, start_date, end_date, dry_run):
    print("\n" + "=" * 78)
    print("DAILY OPTION AGGREGATES")
    print("=" * 78)
    print(f"window: {start_date} .. {end_date}  (endpoint {s3_host})")

    in_databricks = _in_databricks()
    sdk_client = None
    local_root = None
    if not in_databricks:
        from databricks.sdk import WorkspaceClient
        sdk_client = WorkspaceClient(
            profile=os.environ.get("DATABRICKS_CONFIG_PROFILE")
        )
        local_root = tempfile.mkdtemp(prefix="bronze_options_")

    pre_count = spark.sql(
        "SELECT COUNT(*) AS n FROM " + DAY_TABLE
    ).collect()[0]["n"]
    pre_max = spark.sql(
        "SELECT MAX(event_date) AS m FROM " + DAY_TABLE
    ).collect()[0]["m"]

    dates = trading_days(start_date, end_date)

    candidate_total = 0
    new_total = 0
    appended_total = 0
    skipped_success = 0
    entitlement_gap = 0
    failed = 0
    written_files = []

    ingest_ts = datetime.now(timezone.utc)

    for date_str in dates:
        key = s3_key_for_date(date_str)

        if already_ingested(spark, key, DAY_DATASET):
            skipped_success += 1
            continue

        # Probe for entitlement before a full GET/stage.
        try:
            s3.head_object(Bucket=BUCKET, Key=key)
        except Exception as exc:
            if _is_forbidden(exc):
                entitlement_gap += 1
                print(f"  [gap] {date_str} (403 / not entitled)")
                continue
            failed += 1
            print(f"  [err] {date_str} probe: {type(exc).__name__}")
            continue

        if not dry_run:
            log_start(spark, key, DAY_DATASET)
        try:
            vol_file = _stage_file(
                s3, key, sdk_client, local_root,
            )
            if vol_file is None:
                entitlement_gap += 1
                if not dry_run:
                    log_finish(spark, key, DAY_DATASET, 0, error_message="403 / not entitled")
                print(f"  [gap] {date_str} (403 / not entitled)")
                continue
            incoming = _shape_day(spark, vol_file, key, ingest_ts)
            new_rows = _anti_join_new(
                spark, incoming, DAY_KEY_COLUMNS, DAY_TABLE,
                "event_date", start_date, end_date,
            )
            candidate = incoming.count()
            new = new_rows.count()
            candidate_total += candidate
            new_total += new
            if not dry_run and new > 0:
                write_cols = _resolve_write_columns(spark, new_rows, DAY_TABLE)
                new_rows.select(*write_cols) \
                    .write.format("delta").mode("append").saveAsTable(DAY_TABLE)
                appended_total += new
                log_finish(spark, key, DAY_DATASET, new)
                written_files.append((key, new))
            elif not dry_run:
                log_finish(spark, key, DAY_DATASET, 0)
            else:
                print(f"  [dry] {date_str}: candidate={candidate:,} new={new:,}")
        except Exception as exc:
            failed += 1
            if not dry_run:
                log_finish(spark, key, DAY_DATASET, 0, error_message=exc)
            print(f"  [err] {date_str}: {type(exc).__name__}: {str(exc)[:200]}")
        finally:
            try:
                _clear_staged(key, sdk_client)
            except Exception:
                pass

    if local_root is not None:
        shutil.rmtree(local_root, ignore_errors=True)

    post_count = spark.sql(
        "SELECT COUNT(*) AS n FROM " + DAY_TABLE
    ).collect()[0]["n"]
    post_max = spark.sql(
        "SELECT MAX(event_date) AS m FROM " + DAY_TABLE
    ).collect()[0]["m"]

    print("\n  Daily pre-write : rows=%s max_event_date=%s" % (f"{pre_count:,}", pre_max))
    print(f"  dates requested : {len(dates)}")
    print(f"  candidate rows  : {candidate_total:,}")
    print(f"  new (anti-join) : {new_total:,}")
    print(f"  appended rows   : {appended_total:,}")
    print(f"  skipped SUCCESS : {skipped_success}")
    print(f"  entitlement gap : {entitlement_gap}")
    print(f"  failed files    : {failed}")
    print("  Daily post-write: rows=%s max_event_date=%s" % (f"{post_count:,}", post_max))

    return {
        "pre_count": pre_count, "pre_max": pre_max,
        "candidate": candidate_total, "new": new_total, "appended": appended_total,
        "post_count": post_count, "post_max": post_max,
        "entitlement_gap": entitlement_gap, "failed": failed,
        "written_files": written_files,
    }


# -----------------------------------------------------------------------------
# Snapshot ingestion (append + anti-join)
# -----------------------------------------------------------------------------

def _make_polygon_client(polygon_key):
    from polygon import RESTClient
    return RESTClient(polygon_key)


def _retrieve_snapshot_rows(client, universe, snapshot_ts):
    """Retrieve the current options-chain snapshot for each underlying.

    Returns a list of shaped row dicts. Pagination is handled by the polygon
    client iterator. Never prints the key.
    """
    rows = []
    for symbol in universe:
        snapshots = client.list_snapshot_options_chain(
            underlying_asset=symbol,
            params={"limit": SNAPSHOT_PAGE_LIMIT},
        )
        for snap in snapshots:
            row = shape_quote_row(snap, symbol, snapshot_ts, source="polygon")
            if row is not None:
                rows.append(row)
    return rows


def _quotes_schema():
    from pyspark.sql.types import (
        StructType, StructField, StringType, TimestampType, DoubleType,
        LongType, IntegerType, DateType,
    )
    return StructType([
        StructField("option_symbol", StringType(), True),
        StructField("underlying", StringType(), True),
        StructField("expiry", DateType(), True),
        StructField("strike", DoubleType(), True),
        StructField("right", StringType(), True),
        StructField("bid", DoubleType(), True),
        StructField("ask", DoubleType(), True),
        StructField("bid_size", IntegerType(), True),
        StructField("ask_size", IntegerType(), True),
        StructField("midpoint", DoubleType(), True),
        StructField("participant_ts", TimestampType(), True),
        StructField("sequence_id", LongType(), True),
        StructField("source", StringType(), True),
        StructField("raw_payload", StringType(), True),
        StructField("ingest_ts", TimestampType(), True),
        StructField("last_price", DoubleType(), True),
        StructField("volume", LongType(), True),
        StructField("open_interest", DoubleType(), True),
        StructField("implied_volatility", DoubleType(), True),
        StructField("delta", DoubleType(), True),
        StructField("gamma", DoubleType(), True),
        StructField("theta", DoubleType(), True),
        StructField("vega", DoubleType(), True),
    ])


def _run_snapshot(spark, client, dry_run):
    print("\n" + "=" * 78)
    print("OPTIONS-CHAIN SNAPSHOTS (Polygon REST, current snapshot)")
    print("=" * 78)

    pre_count = spark.sql(
        "SELECT COUNT(*) AS n FROM " + QUOTES_TABLE
    ).collect()[0]["n"]
    pre_max = spark.sql(
        "SELECT MAX(participant_ts) AS m FROM " + QUOTES_TABLE
    ).collect()[0]["m"]

    snapshot_ts = datetime.now(timezone.utc)
    rows = _retrieve_snapshot_rows(client, SNAPSHOT_UNIVERSE, snapshot_ts)

    # Normalise: if every row fell back to retrieval time, the shared snapshot_ts
    # is the key; otherwise the provider quote timestamp per row is the key.
    provider_ts_present = sum(
        1 for r in rows if r["participant_ts"] != snapshot_ts
    )
    print(f"  contracts retrieved : {len(rows):,}")
    print(f"  provider-timestamped: {provider_ts_present:,}")
    print(f"  retrieval-timestamped: {len(rows) - provider_ts_present:,}")

    if not rows:
        print("  historical snapshot gap: 2026-09-03 .. execution date is a "
              "documented coverage gap (current-snapshot endpoint only).")
        return {
            "pre_count": pre_count, "pre_max": pre_max,
            "candidate": 0, "new": 0, "appended": 0,
            "post_count": pre_count, "post_max": pre_max,
        }

    from pyspark.sql import functions as F
    incoming = spark.createDataFrame(rows, schema=_quotes_schema())
    dedup = incoming.dropDuplicates(SNAPSHOT_KEY_COLUMNS)
    target_keys = (
        spark.table(QUOTES_TABLE)
        .filter(F.col("participant_ts") >= F.lit("2026-09-03").cast("timestamp"))
        .select(SNAPSHOT_KEY_COLUMNS)
        .distinct()
    )
    new_rows = dedup.join(target_keys, SNAPSHOT_KEY_COLUMNS, "left_anti")

    candidate = incoming.count()
    new_count = new_rows.count()

    if not dry_run and new_count > 0:
        write_cols = _resolve_write_columns(spark, new_rows, QUOTES_TABLE)
        new_rows.select(*write_cols) \
            .write.format("delta").mode("append").saveAsTable(QUOTES_TABLE)

    post_count = spark.sql(
        "SELECT COUNT(*) AS n FROM " + QUOTES_TABLE
    ).collect()[0]["n"]
    post_max = spark.sql(
        "SELECT MAX(participant_ts) AS m FROM " + QUOTES_TABLE
    ).collect()[0]["m"]

    print("\n  Snapshot pre-write : rows=%s max_participant_ts=%s" % (f"{pre_count:,}", pre_max))
    print(f"  candidate rows     : {candidate:,}")
    print(f"  new (anti-join)    : {new_count:,}")
    print(f"  appended rows      : {new_count if not dry_run else 0:,}")
    print("  Snapshot post-write: rows=%s max_participant_ts=%s" % (f"{post_count:,}", post_max))

    return {
        "pre_count": pre_count, "pre_max": pre_max,
        "candidate": candidate, "new": new_count,
        "appended": new_count if not dry_run else 0,
        "post_count": post_count, "post_max": post_max,
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Refresh Bronze options (daily aggregates + chain snapshots)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="Discover/parse/count but write nothing.")
    mode.add_argument("--write", action="store_true",
                      help="Append anti-joined new rows to the Bronze tables.")
    parser.add_argument("--start-date", default=None,
                        help="Inclusive window start (YYYY-MM-DD). Default: "
                             "target max event date + 1 day.")
    parser.add_argument("--end-date", default=END_DATE_DEFAULT,
                        help=f"Inclusive window end (YYYY-MM-DD). Default: {END_DATE_DEFAULT}.")
    return parser


def _derive_start_date(spark):
    max_d = spark.sql(
        "SELECT MAX(event_date) AS m FROM " + DAY_TABLE
    ).collect()[0]["m"]
    if max_d is None:
        return END_DATE_DEFAULT
    return (max_d + timedelta(days=1)).isoformat()


def main(argv):
    args = build_arg_parser().parse_args(argv)
    dry_run = args.dry_run

    spark = _get_spark()
    access_key, secret_key, polygon_key = _load_secrets()

    # --- pre-write snapshot (always reported, even when sources are down) ---
    day_pre_count = spark.sql("SELECT COUNT(*) AS n FROM " + DAY_TABLE).collect()[0]["n"]
    day_pre_max = spark.sql("SELECT MAX(event_date) AS m FROM " + DAY_TABLE).collect()[0]["m"]
    quotes_pre_count = spark.sql("SELECT COUNT(*) AS n FROM " + QUOTES_TABLE).collect()[0]["n"]
    quotes_pre_max = spark.sql("SELECT MAX(participant_ts) AS m FROM " + QUOTES_TABLE).collect()[0]["m"]
    print("=" * 78)
    print("PRE-WRITE SNAPSHOT")
    print("=" * 78)
    print(f"  bronze_options_day   : rows={day_pre_count:,} max_event_date={day_pre_max}")
    print(f"  bronze_options_quotes: rows={quotes_pre_count:,} max_participant_ts={quotes_pre_max}")

    # --- daily aggregates: probe S3 entitlement ---
    s3, s3_host = _detect_s3(access_key, secret_key, DAY_PREFIX + "/")

    if s3 is None:
        print("=" * 78)
        print("MASSIVE FLAT-FILES: access probe FAILED on all endpoints "
              "(403 / entitlement gap).")
        print("No daily aggregate files can be staged or read this run; the "
              "anti-join prevents any partial writes. Nothing was marked "
              "SUCCESS. Classifying the whole window as an entitlement gap.")
        daily = None
    else:
        start_date = args.start_date or _derive_start_date(spark)
        end_date = args.end_date
        daily = _run_daily(
            spark, s3, s3_host, start_date, end_date, dry_run,
        )

    # --- snapshot: probe Polygon entitlement ---
    try:
        client = _make_polygon_client(polygon_key)
        # Validate entitlement with a tiny probe before the full chain.
        probe = client.list_snapshot_options_chain(
            underlying_asset="SPY", params={"limit": 1}
        )
        next(probe)
        snapshot = _run_snapshot(spark, client, dry_run)
    except Exception as exc:
        print("=" * 78)
        print("POLYGON REST SNAPSHOT: access probe FAILED "
              f"({type(exc).__name__}).")
        print("No snapshot can be retrieved; the current snapshot coverage gap "
              "(2026-09-03 .. execution date) remains unrecoverable without a "
              "historical as-of endpoint. Nothing was appended.")
        snapshot = None

    print("\n" + "=" * 78)
    print("REFRESH COMPLETE (dry-run)" if dry_run else "REFRESH COMPLETE (write)")
    print("=" * 78)
    if daily:
        print(f"  daily    : appended={daily['appended']:,} "
              f"candidate={daily['candidate']:,} new={daily['new']:,} "
              f"entitlement_gap={daily['entitlement_gap']} failed={daily['failed']}")
    if snapshot:
        print(f"  snapshot : appended={snapshot['appended']:,} "
              f"candidate={snapshot['candidate']:,} new={snapshot['new']:,}")
    if daily is None or (daily and daily.get("failed", 0) > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
