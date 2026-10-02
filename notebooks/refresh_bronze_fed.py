"""
notebooks/refresh_bronze_fed.py
Bronze refresh: FRED/Federal Reserve series ingestion into Delta.

Target: bootcamp_students.evangoh_capstone.bronze_fed_series
Source: https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>

Usage:
    python notebooks/refresh_bronze_fed.py --dry-run
    python notebooks/refresh_bronze_fed.py --write
"""

import argparse
import csv
import io
import sys
import time
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from pandas.tseries.holiday import USFederalHolidayCalendar


def _easter_sunday(year: int) -> date:
    """Compute Easter Sunday for a given year using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)

CATALOG = "bootcamp_students"
SCHEMA = "evangoh_capstone"
TABLE = "bronze_fed_series"
FQN = f"{CATALOG}.{SCHEMA}.{TABLE}"

END_DATE_DEFAULT = date(2026, 10, 3)

SERIES_CONFIG = {
    # Daily market rates — effectively unrevised, published next business day
    "DFF":     {"desc": "Effective federal funds rate",               "freq": "daily",   "revision_class": "market_rate"},
    "DGS2":    {"desc": "2-year Treasury constant maturity rate",     "freq": "daily",   "revision_class": "market_rate"},
    "DGS10":   {"desc": "10-year Treasury constant maturity rate",    "freq": "daily",   "revision_class": "market_rate"},
    "T10Y2Y":  {"desc": "10-year minus 2-year Treasury spread",       "freq": "daily",   "revision_class": "market_rate"},
    "T10Y3M":  {"desc": "10-year minus 3-month Treasury spread",      "freq": "daily",   "revision_class": "market_rate"},
    "DFEDTARU":{"desc": "Fed funds target range upper bound",        "freq": "daily",   "revision_class": "market_rate"},
    "DFEDTARL":{"desc": "Fed funds target range lower bound",        "freq": "daily",   "revision_class": "market_rate"},
    # Monthly macro — revised after first release
    "CPIAUCSL":{"desc": "CPI, all urban consumers",                  "freq": "monthly", "revision_class": "revised_macro"},
    "CPILFESL":{"desc": "Core CPI",                                  "freq": "monthly", "revision_class": "revised_macro"},
    "UNRATE":  {"desc": "Unemployment rate",                          "freq": "monthly", "revision_class": "revised_macro"},
    "PAYEMS":  {"desc": "Total nonfarm payrolls",                     "freq": "monthly", "revision_class": "revised_macro"},
    "INDPRO":  {"desc": "Industrial production",                      "freq": "monthly", "revision_class": "revised_macro"},
}

DAILY_OVERLAP_DAYS = 14
MONTHLY_OVERLAP_MONTHS = 24
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3
RETRY_BACKOFF = 2.0
FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


# ---------------------------------------------------------------------------
# Date / calendar helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


_NY_TZ = ZoneInfo("America/New_York")


def _us_federal_holidays(start: date, end: date) -> set[date]:
    """Return set of US federal holiday dates in [start, end]."""
    cal = USFederalHolidayCalendar()
    holidays = cal.holidays(start=str(start), end=str(end))
    return {h.date() for h in holidays}


def _bond_market_holidays(start: date, end: date) -> set[date]:
    """Return SIFMA-style bond market holidays in [start, end].

    Federal holidays + Good Friday, minus Columbus Day and Veterans Day.
    Used for market_rate (Treasury H.15) availability only.
    """
    fed = _us_federal_holidays(start, end)
    # Add Good Friday for each year in range
    for year in range(start.year, end.year + 1):
        good_friday = _easter_sunday(year) - timedelta(days=2)
        if start <= good_friday <= end:
            fed.add(good_friday)
    # Remove Columbus Day (2nd Monday in October) and Veterans Day (Nov 11)
    for year in range(start.year, end.year + 1):
        # Columbus Day: 2nd Monday in October
        oct_1 = date(year, 10, 1)
        first_monday = oct_1 + timedelta(days=(7 - oct_1.weekday()) % 7)
        columbus_day = first_monday + timedelta(days=7)
        if start <= columbus_day <= end:
            fed.discard(columbus_day)
        # Veterans Day: November 11
        veterans_day = date(year, 11, 11)
        if start <= veterans_day <= end:
            fed.discard(veterans_day)
    return fed


def _is_ny_business_day(d: date, calendar: str = "federal") -> bool:
    """Monday-Friday, not a holiday per the specified calendar."""
    if d.weekday() >= 5:
        return False
    if calendar == "bond_market":
        holidays = _bond_market_holidays(d, d)
    else:
        holidays = _us_federal_holidays(d, d)
    return d not in holidays


def _next_ny_business_day(d: date, calendar: str = "federal") -> date:
    """Return the next NY business day after d using the specified calendar."""
    nxt = d + timedelta(days=1)
    # Look ahead up to 10 days to cover holiday clusters
    if calendar == "bond_market":
        holidays = _bond_market_holidays(nxt, nxt + timedelta(days=10))
    else:
        holidays = _us_federal_holidays(nxt, nxt + timedelta(days=10))
    while nxt.weekday() >= 5 or nxt in holidays:
        nxt += timedelta(days=1)
    return nxt


def _ny_available_ts(obs_date: date, revision_class: str = "market_rate") -> datetime:
    """Next NY business day after observation_date at 16:30 America/New_York (DST-aware), converted to UTC.

    For market_rate, uses the SIFMA bond-market calendar (federal + Good Friday,
    minus Columbus Day and Veterans Day). For other classes, uses federal calendar.
    """
    cal = "bond_market" if revision_class == "market_rate" else "federal"
    nxt = _next_ny_business_day(obs_date, calendar=cal)
    local_dt = datetime(nxt.year, nxt.month, nxt.day, 16, 30, 0, tzinfo=_NY_TZ)
    return local_dt.astimezone(timezone.utc)


def _overlap_start(max_obs: date, freq: str) -> date:
    """Compute overlap window start from max observation date."""
    if freq == "daily":
        return max_obs - timedelta(days=DAILY_OVERLAP_DAYS)
    else:
        # Monthly: go back MONTHLY_OVERLAP_MONTHS months
        month = max_obs.month - MONTHLY_OVERLAP_MONTHS
        year = max_obs.year
        while month <= 0:
            month += 12
            year -= 1
        return date(year, month, 1)


def _parse_date(s: str) -> Optional[date]:
    """Parse YYYY-MM-DD date string."""
    if not s or not s.strip():
        return None
    try:
        return date.fromisoformat(s.strip())
    except (ValueError, TypeError):
        return None


def _parse_value(raw: str) -> Optional[float]:
    """Parse numeric value; treat '.', empty, non-numeric as None."""
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    if s == ".":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _compute_overlap_dates(series_id: str, max_obs: date) -> date:
    """Return the overlap start date for incremental filtering."""
    cfg = SERIES_CONFIG[series_id]
    return _overlap_start(max_obs, cfg["freq"])


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _download_csv(series_id: str) -> Optional[str]:
    """Download FRED CSV for a series with retry logic."""
    url = f"{FRED_CSV_BASE}?id={series_id}"
    for attempt in range(HTTP_RETRIES):
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
            print(f"  [WARN] {series_id}: HTTP {resp.status_code} (attempt {attempt+1})")
        except requests.RequestException as e:
            print(f"  [WARN] {series_id}: {e} (attempt {attempt+1})")
        if attempt < HTTP_RETRIES - 1:
            time.sleep(RETRY_BACKOFF * (attempt + 1))
    return None


def _validate_csv_header(csv_text: str, series_id: str) -> bool:
    """Validate that CSV has a date column and series_id column."""
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        return False
    header_stripped = [h.strip() for h in header]
    header_upper = [h.upper() for h in header_stripped]
    has_date = "DATE" in header_upper or "OBSERVATION_DATE" in header_upper
    has_series = series_id.upper() in header_upper
    return has_date and has_series


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_csv_rows(
    csv_text: str,
    series_id: str,
    end_date: date,
    overlap_start: Optional[date],
    ingest_ts: datetime,
) -> list[dict]:
    """
    Parse FRED CSV into candidate rows.

    Returns list of dicts with keys matching the target schema.
    Filters by end_date and overlap_start (if set).
    Skips rows with missing/null values.
    """
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    header_stripped = [h.strip() for h in header]
    header_upper = [h.upper() for h in header_stripped]

    # Find date column: try DATE first, then OBSERVATION_DATE
    if "DATE" in header_upper:
        date_idx = header_upper.index("DATE")
    elif "OBSERVATION_DATE" in header_upper:
        date_idx = header_upper.index("OBSERVATION_DATE")
    else:
        return []
    val_idx = header_upper.index(series_id.upper())

    cfg = SERIES_CONFIG[series_id]
    revision_class = cfg["revision_class"]
    freq = cfg["freq"]
    source_url = f"{FRED_CSV_BASE}?id={series_id}"

    rows = []
    for line in reader:
        if len(line) <= max(date_idx, val_idx):
            continue

        obs_date = _parse_date(line[date_idx])
        if obs_date is None:
            continue
        if obs_date > end_date:
            continue
        if overlap_start and obs_date < overlap_start:
            continue

        raw_value = line[val_idx].strip() if line[val_idx] else ""
        value = _parse_value(raw_value)
        if value is None:
            continue

        if revision_class == "market_rate":
            info_ts = _ny_available_ts(obs_date, revision_class="market_rate")
        else:
            info_ts = ingest_ts

        vintage_date = ingest_ts.date()

        rows.append({
            "series_id": series_id,
            "observation_date": obs_date,
            "value": value,
            "vintage_date": vintage_date,
            "information_available_ts": info_ts,
            "source": "fred_csv",
            "source_url": source_url,
            "ingest_ts": ingest_ts,
            "raw_value": raw_value if raw_value != "." else None,
            "revision_class": revision_class,
        })

    return rows


def select_new_rows(
    candidates: list[dict],
    existing_keys: set[tuple],
) -> tuple[list[dict], int, int]:
    """
    Filter candidates against existing keys and deduplicate.

    Returns (new_rows, duplicate_count, overlap_count).
    Natural key: (series_id, observation_date, vintage_date, value)
    """
    seen = set()
    new_rows = []
    dup_count = 0
    overlap_count = 0

    for row in candidates:
        key = (row["series_id"], row["observation_date"], row["vintage_date"], row["value"])
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        if key in existing_keys:
            overlap_count += 1
            continue
        new_rows.append(row)

    return new_rows, dup_count, overlap_count


# ---------------------------------------------------------------------------
# Spark helpers (lazy import for testability)
# ---------------------------------------------------------------------------

def _get_spark():
    """Get or create SparkSession, using serverless when outside Databricks."""
    try:
        from databricks.connect import DatabricksSession
        spark = DatabricksSession.builder.profile("evangohsg").serverless(True).getOrCreate()
        return spark
    except Exception:
        pass
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        spark.sql("SELECT 1").collect()
        return spark
    except Exception:
        return None


def _table_exists(spark, fqn: str) -> bool:
    """Check if a Delta table exists."""
    try:
        spark.sql(f"DESCRIBE TABLE {fqn}").collect()
        return True
    except Exception:
        return False


def _get_existing_keys(spark, fqn: str, series_ids: list[str]) -> tuple[set[tuple], dict[str, date], int]:
    """
    Fetch existing natural keys, per-series max observation dates, and row count.

    Returns (keys_set, max_dates_by_series, total_row_count).
    """
    if not _table_exists(spark, fqn):
        return set(), {}, 0

    keys_df = spark.sql(f"""
        SELECT series_id, observation_date, vintage_date, value
        FROM {fqn}
    """).collect()
    keys = {(r["series_id"], r["observation_date"], r["vintage_date"], r["value"]) for r in keys_df}

    max_df = spark.sql(f"""
        SELECT series_id, MAX(observation_date) AS max_obs
        FROM {fqn}
        GROUP BY series_id
    """).collect()
    max_dates = {r["series_id"]: r["max_obs"] for r in max_df}

    count_df = spark.sql(f"SELECT COUNT(*) AS cnt FROM {fqn}").collect()
    total = count_df[0]["cnt"] if count_df else 0

    return keys, max_dates, total


def _create_table_if_absent(spark, fqn: str):
    """Create the target table if it does not exist."""
    if _table_exists(spark, fqn):
        return
    spark.sql(f"""
        CREATE TABLE {fqn} (
            series_id                STRING     NOT NULL,
            observation_date         DATE       NOT NULL,
            value                    DOUBLE     NOT NULL,
            vintage_date             DATE       NOT NULL,
            information_available_ts TIMESTAMP  NOT NULL,
            source                   STRING     NOT NULL,
            source_url               STRING     NOT NULL,
            ingest_ts                TIMESTAMP  NOT NULL,
            raw_value                STRING,
            revision_class           STRING     NOT NULL
        )
        USING DELTA
    """)


def _append_rows(spark, fqn: str, rows: list[dict]):
    """Append rows to the Delta table using Spark DataFrame."""
    if not rows:
        return
    from pyspark.sql import functions as F
    df = spark.createDataFrame(rows)
    df = df.withColumn("observation_date", F.col("observation_date").cast("date"))
    df = df.withColumn("vintage_date", F.col("vintage_date").cast("date"))
    df.write.format("delta").mode("append").saveAsTable(fqn)


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_refresh(dry_run: bool, start_date: Optional[date] = None, end_date: Optional[date] = None):
    """
    Main entry point for FRED bronze refresh.

    Args:
        dry_run: If True, no table writes are performed.
        start_date: Override start date (default: per-series max + 1 day, or full history).
        end_date: Override end date (default: 2026-10-03).
    """
    if end_date is None:
        end_date = END_DATE_DEFAULT

    mode_label = "DRY-RUN" if dry_run else "WRITE"
    print(f"=== FRED Bronze Refresh — {mode_label} ===")
    print(f"Target: {FQN}")
    print(f"End date: {end_date}")
    print(f"Series count: {len(SERIES_CONFIG)}")
    print()

    spark = _get_spark()
    if spark is None:
        print("[ERROR] Cannot obtain Spark session. Aborting.")
        sys.exit(1)

    series_ids = list(SERIES_CONFIG.keys())
    existing_keys, max_dates, pre_count = _get_existing_keys(spark, FQN, series_ids)

    if not dry_run:
        _create_table_if_absent(spark, FQN)

    all_new_rows = []
    series_results = {}
    failures = []

    ingest_ts = _now_utc()

    for sid in series_ids:
        cfg = SERIES_CONFIG[sid]
        print(f"--- {sid} ({cfg['desc']}, {cfg['freq']}) ---")

        max_obs = max_dates.get(sid)
        if start_date:
            effective_start = start_date
        elif max_obs:
            effective_start = max_obs + timedelta(days=1)
        else:
            effective_start = None  # Full history

        if effective_start and effective_start > end_date:
            print(f"  Already current (max_obs={max_obs}). Skipping.")
            series_results[sid] = {"status": "skipped", "reason": "already current"}
            continue

        overlap_start = None
        if max_obs:
            overlap_start = _compute_overlap_dates(sid, max_obs)
            print(f"  Overlap start: {overlap_start} (max_obs={max_obs})")

        csv_text = _download_csv(sid)
        if csv_text is None:
            msg = f"Failed to download CSV for {sid}"
            print(f"  [FAIL] {msg}")
            failures.append({"series_id": sid, "error": msg})
            series_results[sid] = {"status": "failed", "error": msg}
            continue

        if not _validate_csv_header(csv_text, sid):
            msg = f"Invalid CSV header for {sid}"
            print(f"  [FAIL] {msg}")
            failures.append({"series_id": sid, "error": msg})
            series_results[sid] = {"status": "failed", "error": msg}
            continue

        candidates = parse_csv_rows(csv_text, sid, end_date, overlap_start, ingest_ts)
        source_rows = len(candidates)

        new_rows, dup_count, overlap_count = select_new_rows(candidates, existing_keys)

        print(f"  Source rows (filtered): {source_rows}")
        print(f"  Duplicates (within batch): {dup_count}")
        print(f"  Overlap (existing keys): {overlap_count}")
        print(f"  New rows: {len(new_rows)}")

        series_results[sid] = {
            "status": "ok",
            "source_rows": source_rows,
            "duplicates": dup_count,
            "overlap": overlap_count,
            "new_rows": len(new_rows),
        }

        all_new_rows.extend(new_rows)

    # ── Write ─────────────────────────────────────────────────────────────
    appended = 0
    if not dry_run and all_new_rows:
        print(f"\nAppending {len(all_new_rows)} rows...")
        _append_rows(spark, FQN, all_new_rows)
        appended = len(all_new_rows)
        print(f"  Appended: {appended}")

    post_count = pre_count + appended

    # ── Report ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"REPORT — {mode_label}")
    print(f"{'='*60}")
    print(f"Pre-write row count:  {pre_count}")
    print(f"Candidate rows:       {len(all_new_rows)}")
    print(f"Appended rows:        {appended}")
    print(f"Post-write row count: {post_count}")
    print(f"Max source date:      {end_date}")
    print()

    for sid, res in series_results.items():
        if res["status"] == "ok":
            print(f"  {sid}: {res['new_rows']} new, {res['overlap']} overlap, {res['duplicates']} dups")
        elif res["status"] == "skipped":
            print(f"  {sid}: skipped ({res['reason']})")
        else:
            print(f"  {sid}: FAILED — {res['error']}")

    if failures:
        print(f"\n[WARN] {len(failures)} series failed.")
        for f in failures:
            print(f"  - {f['series_id']}: {f['error']}")
        return 1

    print(f"\n[OK] FRED bronze refresh complete ({mode_label}).")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="FRED Bronze Refresh")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Discovery and validation only, no writes")
    group.add_argument("--write", action="store_true", help="Validate and append new rows")
    parser.add_argument("--start-date", type=str, default=None, help="Override start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="Override end date (YYYY-MM-DD)")

    args = parser.parse_args()

    start = date.fromisoformat(args.start_date) if args.start_date else None
    end = date.fromisoformat(args.end_date) if args.end_date else None

    rc = run_refresh(dry_run=args.dry_run, start_date=start, end_date=end)
    sys.exit(rc)


if __name__ == "__main__":
    main()