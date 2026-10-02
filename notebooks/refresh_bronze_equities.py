# Databricks notebook source
# COMMAND ----------
"""
refresh_bronze_equities.py — Bronze equities refresh lane (Massive flat files).

Append-only incremental refresh of two independent Bronze sources:

  * us_stocks_sip/minute_aggs_v1  -> bootcamp_students.evangoh_capstone.bronze_ohlcv
  * us_stocks_sip/day_aggs_v1     -> bootcamp_students.evangoh_capstone.bronze_ohlcv_day

Runs as a Databricks notebook task. Parameters are read from widgets
(overridable via job `base_parameters`):

  * mode       : "dry-run" (default) | "write"
  * start_date : optional YYYY-MM-DD override; defaults to date(max(event_ts)) + 1 day
  * end_date   : defaults to "2026-10-03"

All Bronze writes are append-only. No UPDATE / DELETE / OVERWRITE / replaceWhere /
MERGE-WHEN-MATCHED is issued against the Bronze tables. Only the operational
ingestion-log table (operational metadata, not Bronze history) is status-updated.

The pure parsing helpers in this file must stay importable without a Spark,
boto3 or dbutils context so the lane's unit tests can exercise them directly.
"""
import csv
import gzip
import io
import json
import re
from datetime import date, datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CATALOG_SCHEMA = "bootcamp_students.evangoh_capstone"
BUCKET = "flatfiles"
ENDPOINT = "https://files.massive.com"

MINUTE_PREFIX = "us_stocks_sip/minute_aggs_v1"
DAY_PREFIX = "us_stocks_sip/day_aggs_v1"

BRONZE_MINUTE_TABLE = f"{CATALOG_SCHEMA}.bronze_ohlcv"
BRONZE_DAY_TABLE = f"{CATALOG_SCHEMA}.bronze_ohlcv_day"
MINUTE_LOG_TABLE = f"{CATALOG_SCHEMA}.massive_ingestion_log"
DAY_LOG_TABLE = f"{CATALOG_SCHEMA}.massive_daily_ingestion_log"

SOURCE = "massive_flatfile"
DEFAULT_END_DATE = "2026-10-03"

# Natural key for both market tables: (symbol, event_ts, timespan).
# source_file is lineage only and is not part of the bar identity.
KEY_COLUMNS = ["symbol", "event_ts", "timespan"]

_LOG_SCHEMA = ("source_file string, dataset string, status string, row_count long, "
               "started_at timestamp, completed_at timestamp, error_message string")

# ---------------------------------------------------------------------------
# Minute ticker universe (matches the archived filtered loader).
# Daily ingestion remains full-market (no filter).
# ---------------------------------------------------------------------------
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "MRVL", "MU", "SNDK",
    "AMAT", "LRCX", "KLAC", "ASML", "TSM", "ON", "MPWR",
    "NXPI", "ADI", "MCHP", "SWKS", "QRVO", "ENTG", "CRUS",
    "WOLF", "ONTO", "ACLS", "SLAB", "STM",
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLE",
    "JPM", "GS", "BAC", "MS",
    "NFLX", "CRM", "UBER", "COIN", "XOM", "JNJ", "V", "WMT",
]

_OBJECT_KEY_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.csv\.gz$")


class ForbiddenError(Exception):
    """Raised when a Massive object is outside the current entitlement window."""


# ---------------------------------------------------------------------------
# Pure helpers (no Spark / boto3 / dbutils dependency)
# ---------------------------------------------------------------------------
def ns_to_ts(value):
    """Convert a Massive nanosecond Unix epoch to a naive UTC datetime.

    Naive UTC is used deliberately: timestamps are handled in UTC internally
    and Spark stores naive values as-is in UTC. Returns None on bad input.
    """
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(
            int(value) / 1_000_000_000, tz=timezone.utc
        ).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        return None


def as_float(row, key):
    value = row.get(key)
    return float(value) if value not in (None, "") else None


def as_int(row, key):
    value = row.get(key)
    return int(float(value)) if value not in (None, "") else None


def parse_object_key_date(key):
    """Extract the YYYY-MM-DD date from a Massive object key, or None."""
    match = _OBJECT_KEY_DATE_RE.search(key or "")
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def key_in_window(key, start_date, end_date):
    d = parse_object_key_date(key)
    return d is not None and start_date <= d <= end_date


def parse_minute_file(body, key, ingest_ts, tickers):
    """Stream one minute aggregate gzip CSV into a list of Bronze row dicts.

    Applies the ticker-universe filter (tickers). Rows without a parseable
    `window_start` timestamp are dropped.
    """
    rows = []
    with gzip.GzipFile(fileobj=body, mode="rb") as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text_stream:
            reader = csv.DictReader(text_stream)
            for r in reader:
                ticker = (r.get("ticker") or "").strip()
                if not ticker:
                    continue
                if tickers and ticker not in tickers:
                    continue
                event_ts = ns_to_ts(r.get("window_start"))
                if event_ts is None:
                    continue
                rows.append({
                    "symbol": ticker,
                    "event_ts": event_ts,
                    "open": as_float(r, "open"),
                    "high": as_float(r, "high"),
                    "low": as_float(r, "low"),
                    "close": as_float(r, "close"),
                    "volume": as_int(r, "volume"),
                    "vwap": as_float(r, "vwap"),
                    "trade_count": as_int(r, "transactions"),
                    "timespan": "minute",
                    "source": SOURCE,
                    "raw_payload": None,
                    "ingest_ts": ingest_ts,
                    "source_file": key,
                })
    return rows


def parse_day_file(body, key, ingest_ts, tickers=None):
    """Stream one daily aggregate gzip CSV into a list of Bronze row dicts.

    Full-market: no ticker filter. `tickers` is accepted for a uniform call
    signature but ignored. Derives event_date / event_year from event_ts.
    """
    rows = []
    with gzip.GzipFile(fileobj=body, mode="rb") as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text_stream:
            reader = csv.DictReader(text_stream)
            for r in reader:
                symbol = (r.get("ticker") or "").strip()
                if not symbol:
                    continue
                event_ts = ns_to_ts(r.get("window_start"))
                if event_ts is None:
                    continue
                rows.append({
                    "symbol": symbol,
                    "event_ts": event_ts,
                    "event_date": event_ts.date(),
                    "event_year": event_ts.year,
                    "open": as_float(r, "open"),
                    "high": as_float(r, "high"),
                    "low": as_float(r, "low"),
                    "close": as_float(r, "close"),
                    "volume": as_int(r, "volume"),
                    "vwap": as_float(r, "vwap"),
                    "trade_count": as_int(r, "transactions"),
                    "timespan": "day",
                    "source": SOURCE,
                    "source_file": key,
                    "ingest_ts": ingest_ts,
                })
    return rows


def _is_forbidden(exc):
    code = ""
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        code = (resp.get("Error") or {}).get("Code") or ""
    if code in ("403", "AccessDenied", "Forbidden"):
        return True
    msg = str(exc)
    return "403" in msg or "Forbidden" in msg or "AccessDenied" in msg


# COMMAND ----------
# Runtime helpers (Spark / dbutils / boto3 present only when run as a notebook)


def _now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_params():
    mode = "dry-run"
    start = ""
    end = DEFAULT_END_DATE
    try:
        mode = (dbutils.widgets.get("mode", "dry-run") or "").strip() or "dry-run"
        start = (dbutils.widgets.get("start_date", "") or "").strip()
        end = (dbutils.widgets.get("end_date", DEFAULT_END_DATE) or "").strip() or DEFAULT_END_DATE
    except Exception:
        pass
    return mode, start, end


def _minute_schema(T):
    return T.StructType([
        T.StructField("symbol", T.StringType(), False),
        T.StructField("event_ts", T.TimestampType(), True),
        T.StructField("open", T.DoubleType(), True),
        T.StructField("high", T.DoubleType(), True),
        T.StructField("low", T.DoubleType(), True),
        T.StructField("close", T.DoubleType(), True),
        T.StructField("volume", T.LongType(), True),
        T.StructField("vwap", T.DoubleType(), True),
        T.StructField("trade_count", T.IntegerType(), True),
        T.StructField("timespan", T.StringType(), False),
        T.StructField("source", T.StringType(), False),
        T.StructField("raw_payload", T.StringType(), True),
        T.StructField("ingest_ts", T.TimestampType(), False),
        T.StructField("source_file", T.StringType(), True),
    ])


def _day_schema(T):
    return T.StructType([
        T.StructField("symbol", T.StringType(), False),
        T.StructField("event_ts", T.TimestampType(), True),
        T.StructField("event_date", T.DateType(), True),
        T.StructField("event_year", T.IntegerType(), True),
        T.StructField("open", T.DoubleType(), True),
        T.StructField("high", T.DoubleType(), True),
        T.StructField("low", T.DoubleType(), True),
        T.StructField("close", T.DoubleType(), True),
        T.StructField("volume", T.LongType(), True),
        T.StructField("vwap", T.DoubleType(), True),
        T.StructField("trade_count", T.LongType(), True),
        T.StructField("timespan", T.StringType(), False),
        T.StructField("source", T.StringType(), False),
        T.StructField("source_file", T.StringType(), True),
        T.StructField("ingest_ts", T.TimestampType(), False),
    ])


# COMMAND ----------


def main():
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql import types as T

    try:
        from delta.tables import DeltaTable
    except Exception:
        DeltaTable = None

    spark = SparkSession.builder.getOrCreate()
    mode, start_override, end_iso = _get_params()
    end_date = date.fromisoformat(end_iso)

    access_key = dbutils.secrets.get(scope="evangoh_capstone", key="massive_s3_access_key")
    secret_key = dbutils.secrets.get(scope="evangoh_capstone", key="massive_s3_secret_key")

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=120,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )

    def list_s3_files(prefix, start_date, stop_date):
        files = []
        paginator = s3.get_paginator("list_objects_v2")
        year_months = set()
        d = start_date
        while d <= stop_date:
            year_months.add((d.year, d.month))
            d = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
        for year, month in sorted(year_months):
            mprefix = f"{prefix}/{year}/{month:02d}/"
            try:
                for page in paginator.paginate(Bucket=BUCKET, Prefix=mprefix):
                    for obj in page.get("Contents", []):
                        key = obj.get("Key", "")
                        if not key.endswith(".csv.gz"):
                            continue
                        kd = parse_object_key_date(key)
                        if kd is not None and start_date <= kd <= stop_date:
                            files.append((key, obj.get("Size", 0), kd))
            except Exception as exc:
                if _is_forbidden(exc):
                    print(f"  skip prefix {mprefix}: not authorized by entitlement")
                    continue
                raise
        return sorted(files, key=lambda x: x[0])

    def get_body(key):
        try:
            return s3.get_object(Bucket=BUCKET, Key=key)["Body"]
        except ClientError as exc:
            if _is_forbidden(exc):
                raise ForbiddenError(key) from exc
            raise

    def already_ingested(log_table, source_file, dataset):
        return (
            spark.table(log_table)
            .filter(
                (F.col("source_file") == source_file)
                & (F.col("dataset") == dataset)
                & (F.col("status") == "SUCCESS")
            )
            .limit(1)
            .count()
        ) > 0

    def log_start(log_table, source_file, dataset, started_at):
        df = spark.createDataFrame(
            [(source_file, dataset, "RUNNING", 0, started_at, None, None)],
            _LOG_SCHEMA,
        )
        df.write.format("delta").mode("append").saveAsTable(log_table)

    def log_finish(log_table, source_file, dataset, started_at, row_count, error):
        now = _now_utc()
        if error is None:
            updates = {
                "status": F.lit("SUCCESS"),
                "row_count": F.lit(int(row_count)),
                "completed_at": F.lit(now),
            }
        else:
            updates = {
                "status": F.lit("FAILED"),
                "row_count": F.lit(int(row_count)),
                "completed_at": F.lit(now),
                "error_message": F.lit(str(error)[:4000]),
            }
        if DeltaTable is not None:
            cond = (
                (F.col("source_file") == source_file)
                & (F.col("dataset") == dataset)
                & (F.col("status") == "RUNNING")
                & (F.col("started_at") == F.lit(started_at))
            )
            DeltaTable.forName(spark, log_table).update(cond, updates)
        else:
            status = "SUCCESS" if error is None else "FAILED"
            err = None if error is None else str(error)[:4000]
            df = spark.createDataFrame(
                [(source_file, dataset, status, int(row_count), started_at, now, err)],
                _LOG_SCHEMA,
            )
            df.write.format("delta").mode("append").saveAsTable(log_table)

    def run_dataset(name, prefix, target, log_table, timespan, tickers, parse_fn, schema):
        row = (
            spark.table(target)
            .agg(F.count("*").alias("n"), F.max("event_ts").alias("mx"))
            .collect()[0]
        )
        pre_count = int(row["n"] or 0)
        max_ts = row["mx"]
        if start_override:
            start_date = date.fromisoformat(start_override)
        elif max_ts is not None:
            start_date = max_ts.date() + timedelta(days=1)
        else:
            start_date = date(2021, 1, 1)

        summary = {
            "name": name,
            "prefix": prefix,
            "target": target,
            "pre_count": pre_count,
            "max_event_ts": str(max_ts),
            "start_date": str(start_date),
            "end_date": str(end_date),
            "files_found": 0,
            "skipped_success": 0,
            "inaccessible": 0,
            "failed": 0,
            "total_candidate": 0,
            "total_duplicate": 0,
            "total_new": 0,
            "total_appended": 0,
            "files": [],
        }

        files = list_s3_files(prefix, start_date, end_date)
        summary["files_found"] = len(files)

        # Prune the anti-join key set to the window (plus a 2-day buffer).
        # Materialize once via count() so Delta caches the scan; subsequent
        # anti-join evaluations reuse the cached plan instead of re-reading
        # the target table from storage on every file iteration.
        buffer_start = datetime.combine(start_date - timedelta(days=2), datetime.min.time())
        existing_keys = (
            spark.table(target)
            .select(KEY_COLUMNS)
            .filter(F.col("event_ts") >= F.lit(buffer_start))
            .distinct()
        )
        existing_keys_count = existing_keys.count()
        print(f"  Anti-join key cache: {existing_keys_count:,} existing keys in window")

        for key, size, kd in files:
            fs = {"key": key, "date": str(kd), "size": size}
            if already_ingested(log_table, key, prefix):
                summary["skipped_success"] += 1
                fs["status"] = "skipped_success"
                summary["files"].append(fs)
                continue

            try:
                body = get_body(key)
            except ForbiddenError:
                summary["inaccessible"] += 1
                fs["status"] = "inaccessible"
                summary["files"].append(fs)
                continue
            except Exception as exc:
                summary["failed"] += 1
                fs["status"] = "error:" + type(exc).__name__
                summary["files"].append(fs)
                continue

            ingest_ts = _now_utc()
            rows = parse_fn(body, key, ingest_ts, tickers)
            candidate = len(rows)
            fs["candidate"] = candidate
            summary["total_candidate"] += candidate

            if candidate == 0:
                fs["status"] = "empty"
                summary["files"].append(fs)
                continue

            incoming = spark.createDataFrame(rows, schema=schema)
            incoming = incoming.dropDuplicates(KEY_COLUMNS)
            deduped = incoming.count()
            duplicates = candidate - deduped
            new_rows = incoming.join(existing_keys, KEY_COLUMNS, "left_anti")
            new_count = new_rows.count()

            summary["total_duplicate"] += duplicates
            summary["total_new"] += new_count
            fs["duplicate"] = duplicates
            fs["new"] = new_count

            if mode != "write":
                fs["status"] = "dry_run"
                summary["files"].append(fs)
                continue

            started_at = _now_utc()
            log_start(log_table, key, prefix, started_at)
            try:
                if new_count > 0:
                    new_rows.write.format("delta").mode("append").saveAsTable(target)
                    summary["total_appended"] += new_count
                    fs["appended"] = new_count
                else:
                    fs["appended"] = 0

                # Verify the append landed before marking SUCCESS.
                in_target = (
                    spark.table(target)
                    .filter(F.col("source_file") == key)
                    .count()
                )
                if in_target < new_count:
                    raise RuntimeError(
                        f"post-write verification failed: expected >= {new_count} "
                        f"rows for {key}, found {in_target}"
                    )
                log_finish(log_table, key, prefix, started_at, new_count, None)
                fs["status"] = "success"
            except Exception as exc:
                log_finish(log_table, key, prefix, started_at, new_count, exc)
                summary["failed"] += 1
                fs["status"] = "error:" + type(exc).__name__
            summary["files"].append(fs)

        post = (
            spark.table(target)
            .agg(F.count("*").alias("n"), F.max("event_ts").alias("mx"))
            .collect()[0]
        )
        summary["post_count"] = int(post["n"] or 0)
        summary["post_max_event_ts"] = str(post["mx"])
        return summary

    report = {"mode": mode, "end_date": str(end_date), "datasets": {}}

    report["datasets"]["minute"] = run_dataset(
        "minute", MINUTE_PREFIX, BRONZE_MINUTE_TABLE, MINUTE_LOG_TABLE,
        "minute", TICKERS, parse_minute_file, _minute_schema(T),
    )
    report["datasets"]["day"] = run_dataset(
        "day", DAY_PREFIX, BRONZE_DAY_TABLE, DAY_LOG_TABLE,
        "day", None, parse_day_file, _day_schema(T),
    )

    print(json.dumps(report, indent=2))
    dbutils.notebook.exit(json.dumps(report))


# COMMAND ----------

if __name__ == "__main__":
    main()
