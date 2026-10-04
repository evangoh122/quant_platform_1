"""
notebooks/refresh_bronze_cot.py
CFTC Traders-in-Financial-Futures (TFF) Bronze Refresh — append-only incremental.

Targets:
  bootcamp_students.evangoh_capstone.bronze_cftc_com  (futures + options combined)
  bootcamp_students.evangoh_capstone.bronze_cftc_fut  (futures only)

Usage:
  python notebooks/refresh_bronze_cot.py --dry-run
  python notebooks/refresh_bronze_cot.py --write
  python notebooks/refresh_bronze_cot.py --dry-run --start-date 2026-09-01 --end-date 2026-10-03
"""

import argparse
import io
import os
import sys
import zipfile
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Tuple

import pandas as pd
import requests

# Lazy Spark imports — PySpark may not be installed in local test environments.
# Import at function call sites inside the Databricks / Connect runtime.
SparkSession = None
DataFrame = None
F = None
T = None


def _ensure_spark_imports():
    global SparkSession, DataFrame, F, T
    if SparkSession is None:
        from pyspark.sql import functions as _F, types as _T
        try:
            from databricks.connect import DatabricksSession as _SS
        except ImportError:
            from pyspark.sql import SparkSession as _SS
        SparkSession = _SS
        DataFrame = _SS  # placeholder, actual DataFrame type resolved at runtime
        F = _F
        T = _T


# =============================================================================
# CONFIG
# =============================================================================

CATALOG = "bootcamp_students"
SCHEMA = "evangoh_capstone"
CATALOG_SCHEMA = f"{CATALOG}.{SCHEMA}"

DATASETS = [
    {
        "name": "com_fin",
        "url_stem": "com_fin_txt",
        "table": f"{CATALOG_SCHEMA}.bronze_cftc_com",
    },
    {
        "name": "fut_fin",
        "url_stem": "fut_fin_txt",
        "table": f"{CATALOG_SCHEMA}.bronze_cftc_fut",
    },
]

BASE_URL = "https://www.cftc.gov/files/dea/history"
HTTP_TIMEOUT = 120

def _build_cot_headers() -> dict:
    """Build CFTC User-Agent headers. Fail closed on missing email."""
    email = os.getenv("CFTC_USER_EMAIL", "")
    if not email or "example" in email.lower():
        raise ValueError(
            "CFTC_USER_EMAIL must be set to a valid contact email. "
            "Set it from environment or Databricks secret."
        )
    return {"User-Agent": f"capstone-research (evangoh) {email}"}

# Release-timestamp policy: COT is as-of-Tuesday, published Friday ~15:30 ET.
# RELEASE_SAFETY_DAYS=3 → assume availability the following Monday 15:30 ET.
# release_date = report_date + 6 days (3 nominal + 3 safety).
# This avoids holiday-week lookahead at the cost of a few days of freshness.
RELEASE_SAFETY_DAYS = 3
RELEASE_HOUR_ET = 15
RELEASE_MINUTE_ET = 30
RELEASE_TZ = "America/New_York"

REPORT_DATE_COL = "Report_Date_as_YYYY-MM-DD"

TARGET_YEAR = 2026
DEFAULT_END_DATE = date(2026, 10, 3)


# =============================================================================
# HELPERS — download and parse
# =============================================================================

def cftc_url(url_stem: str, year: int) -> str:
    """Build the annual CFTC flat-file URL."""
    return f"{BASE_URL}/{url_stem}_{year}.zip"


def download_year(url_stem: str, year: int) -> Tuple[Optional[pd.DataFrame], str]:
    """Fetch one annual TFF zip and return (raw_pandas_df, url).

    Returns (None, url) when the year is not posted (404).
    Every column is read as STRING with empties preserved, so Bronze keeps the
    source verbatim and no NaN-float contamination sneaks in.
    """
    url = cftc_url(url_stem, year)
    resp = requests.get(url, headers=_build_cot_headers(), timeout=HTTP_TIMEOUT)

    if resp.status_code == 404:
        return None, url
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        member = zf.namelist()[0]
        with zf.open(member) as fh:
            pdf = pd.read_csv(
                fh,
                dtype=str,
                keep_default_na=False,
                na_values=[],
                low_memory=False,
            )

    return pdf, url


def sanitize_columns(pdf: pd.DataFrame) -> pd.DataFrame:
    """Replace characters disallowed in Delta column names with underscores.

    The TFF long-format headers are already underscore-safe, so this is a
    defensive normalization.  It also strips leading/trailing whitespace.
    """
    bad = " ,;{}()\n\t="
    renamed = {}
    for c in pdf.columns:
        clean = c.strip()
        for ch in bad:
            clean = clean.replace(ch, "_")
        renamed[c] = clean
    return pdf.rename(columns=renamed)


# =============================================================================
# HELPERS — release timestamp
# =============================================================================

def compute_release_ts(report_date_col: "pd.Series") -> "pd.Series":
    """Compute conservative release timestamp for a pandas date column.

    COT/TFF is an as-of-Tuesday snapshot nominally published Friday ~15:30 ET.
    With RELEASE_SAFETY_DAYS=3 we push to the following Monday to avoid
    holiday-week lookahead.

    Returns a pandas Series of naive UTC timestamps (timezone info stripped
    so PySpark createDataFrame handles them cleanly).
    """
    import pytz

    release_offsets = timedelta(days=3 + RELEASE_SAFETY_DAYS)
    release_time = datetime.strptime(
        f"{RELEASE_HOUR_ET:02d}:{RELEASE_MINUTE_ET:02d}", "%H:%M"
    ).time()

    et_tz = pytz.timezone(RELEASE_TZ)

    results = []
    for rd in report_date_col:
        if pd.isna(rd):
            results.append(None)
            continue
        rd_date = rd if isinstance(rd, date) else rd.date()
        release_date = rd_date + release_offsets
        release_local = datetime.combine(release_date, release_time)
        release_localized = et_tz.localize(release_local)
        # Convert to naive UTC ISO string for PySpark compatibility
        utc_naive = release_localized.astimezone(pytz.utc).replace(tzinfo=None)
        results.append(utc_naive.strftime("%Y-%m-%dT%H:%M:%S"))

    return pd.Series(results)


# =============================================================================
# HELPERS — Spark shaping
# =============================================================================

def to_bronze(pdf: pd.DataFrame, dataset: str, url: str, ingest_ts: datetime, spark):
    """Attach report_date / release_ts / lineage to the raw string frame.

    All source columns remain StringType for Bronze fidelity.
    Returns a PySpark DataFrame.
    """
    _ensure_spark_imports()

    if REPORT_DATE_COL not in pdf.columns:
        raise RuntimeError(
            f"{dataset}: expected column '{REPORT_DATE_COL}' not found. "
            f"Columns seen: {list(pdf.columns[:8])}..."
        )

    pdf = sanitize_columns(pdf)

    # Create Spark DataFrame from raw string columns only
    sdf = spark.createDataFrame(pdf)

    # Add derived columns using Spark SQL functions (matches archive approach)
    report_date = F.to_date(F.col(REPORT_DATE_COL), "yyyy-MM-dd")

    # Nominal Friday (report_date + 6 days = report_date + 3 + RELEASE_SAFETY_DAYS)
    # at 15:30 ET, converted to a UTC instant.
    release_date = F.date_add(report_date, 3 + RELEASE_SAFETY_DAYS)
    release_local = F.concat(
        release_date.cast("string"),
        F.lit(f" {RELEASE_HOUR_ET:02d}:{RELEASE_MINUTE_ET:02d}:00"),
    )
    release_ts = F.to_utc_timestamp(release_local, RELEASE_TZ)

    sdf = (
        sdf
        .withColumn("report_date", report_date)
        .withColumn("report_year", F.year(report_date))
        .withColumn("release_ts", release_ts)
        .withColumn("source_dataset", F.lit(dataset))
        .withColumn("source_file", F.lit(url))
        .withColumn("ingest_ts", F.lit(ingest_ts))
    )

    return sdf


# =============================================================================
# HELPERS — validation
# =============================================================================

def validate_contract_code_column(df, dataset: str) -> str:
    """Locate the CFTC contract market code column in the DataFrame.

    Tries common sanitized variants of 'CFTC_Contract_Market_Code'.
    Raises RuntimeError if none found — this is a dry-run gate.
    """
    candidates = [
        "CFTC_Contract_Market_Code",
        "CFTC_Contract_Market_Code_",
        "CFTC_Contract_Market_Code  ",
        "cftc_contract_market_code",
    ]
    cols_lower = {c.lower().strip(): c for c in df.columns}

    for candidate in candidates:
        key = candidate.lower().strip()
        if key in cols_lower:
            return cols_lower[key]

    # Fuzzy fallback: look for any column containing 'contract_market_code'
    for col_lower, col_orig in cols_lower.items():
        if "contract_market_code" in col_lower:
            return col_orig

    raise RuntimeError(
        f"{dataset}: no stable CFTC contract market code column found. "
        f"Columns seen: {list(df.columns)[:15]}..."
    )


def validate_bronze_df(df, dataset: str, contract_code_col: str, target_year: int):
    """Validate non-null report_date, contract code, expected year, and release_ts."""
    _ensure_spark_imports()
    # report_date non-null
    n_null_date = df.filter(F.col("report_date").isNull()).limit(1).count()
    if n_null_date:
        raise RuntimeError(f"{dataset}: null report_date values present.")

    # contract code non-null
    n_null_code = df.filter(F.col(contract_code_col).isNull() | (F.col(contract_code_col) == "")).limit(1).count()
    if n_null_code:
        raise RuntimeError(f"{dataset}: null/empty {contract_code_col} values present.")

    # year match
    n_bad_year = df.filter(F.col("report_year") != F.lit(target_year)).limit(1).count()
    if n_bad_year:
        raise RuntimeError(f"{dataset}: rows with report_year != {target_year}.")

    # release_ts non-null
    n_null_release = df.filter(F.col("release_ts").isNull()).limit(1).count()
    if n_null_release:
        raise RuntimeError(f"{dataset}: null release_ts values present.")

    # no future report dates
    n_future = df.filter(F.col("report_date") > F.lit(DEFAULT_END_DATE)).limit(1).count()
    if n_future:
        raise RuntimeError(f"{dataset}: report dates after {DEFAULT_END_DATE} present.")


# =============================================================================
# HELPERS — idempotency
# =============================================================================

def get_target_stats(spark, table: str) -> Tuple[int, Optional[date]]:
    """Return (row_count, max_report_date) for a target table."""
    if not spark.catalog.tableExists(table):
        return 0, None
    row = spark.sql(
        f"SELECT COUNT(*) AS cnt, MAX(report_date) AS max_rd FROM {table}"
    ).collect()[0]
    return row["cnt"], row["max_rd"]


def anti_join_new_rows(
    incoming,
    target,
    key_cols: list,
    contract_code_col: str,
):
    """Left anti-join: keep only rows whose natural key does not exist in target.

    Natural key: (source_dataset, <contract_code_col>, report_date)
    """
    full_key = ["source_dataset", contract_code_col, "report_date"]
    # Deduplicate incoming batch
    incoming = incoming.dropDuplicates(full_key)

    # Anti-join against target keys
    target_keys = target.select(*full_key).distinct()
    new_rows = incoming.join(target_keys, on=full_key, how="left_anti")
    return new_rows


def detect_revision_conflicts(
    incoming,
    target,
    contract_code_col: str,
) -> int:
    """Count rows where the natural key already exists in target.

    These are not exact duplicates (values may differ) — report as revision conflicts.
    """
    full_key = ["source_dataset", contract_code_col, "report_date"]
    incoming_keys = incoming.select(*full_key).distinct()
    existing_keys = target.select(*full_key).distinct()
    conflicts = incoming_keys.join(existing_keys, on=full_key, how="inner")
    return conflicts.count()


# =============================================================================
# MAIN REFRESH LOGIC
# =============================================================================

def filter_report_window(
    pdf: "pd.DataFrame", start_date: date, end_date: date
) -> "pd.DataFrame":
    """Filter a raw CFTC DataFrame to rows whose report date falls in [start_date, end_date].

    Parses the report-date column, strips whitespace, and applies the
    inclusive date-range filter used by the incremental refresh.

    Raises KeyError if ``REPORT_DATE_COL`` is not present in *pdf*.
    """
    if REPORT_DATE_COL not in pdf.columns:
        raise KeyError(f"Column '{REPORT_DATE_COL}' not found")

    if len(pdf) == 0:
        return pdf.copy()

    pdf = pdf.copy()
    pdf[REPORT_DATE_COL] = pdf[REPORT_DATE_COL].astype(str).str.strip()
    parsed = pd.to_datetime(
        pdf[REPORT_DATE_COL], format="%Y-%m-%d", errors="coerce"
    )
    pdf["_parsed_date"] = parsed

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    mask = (parsed >= start_ts) & (parsed <= end_ts)
    return pdf.loc[mask].drop(columns=["_parsed_date"]).copy()


def refresh_dataset(
    spark,
    ds: dict,
    start_date: date,
    end_date: date,
    dry_run: bool,
    target_year: int,
) -> dict:
    """Refresh one CFTC dataset (com_fin or fut_fin).

    Returns a report dict with counts and status.
    """
    _ensure_spark_imports()
    ds_name = ds["name"]
    url_stem = ds["url_stem"]
    table = ds["table"]
    table_short = table.split(".")[-1]

    report = {
        "dataset": ds_name,
        "table": table_short,
        "status": "PENDING",
        "pre_count": 0,
        "pre_max_date": None,
        "candidate_count": 0,
        "duplicate_count": 0,
        "conflict_count": 0,
        "new_count": 0,
        "post_count": 0,
        "post_max_date": None,
        "source_file": None,
        "error": None,
    }

    try:
        # 1. Pre-snapshot
        pre_count, pre_max_date = get_target_stats(spark, table)
        report["pre_count"] = pre_count
        report["pre_max_date"] = str(pre_max_date) if pre_max_date else "N/A"

        # 2. Download current year
        pdf, url = download_year(url_stem, target_year)
        report["source_file"] = url

        if pdf is None:
            report["status"] = "SKIPPED"
            report["error"] = f"{target_year} file not posted (404)"
            return report
        if len(pdf) == 0:
            report["status"] = "SKIPPED"
            report["error"] = f"{target_year} file is empty"
            return report

        # 3. Filter to incremental window
        try:
            pdf_filtered = filter_report_window(pdf, start_date, end_date)
        except KeyError as exc:
            report["status"] = "FAILED"
            report["error"] = str(exc)
            return report

        if len(pdf_filtered) == 0:
            report["status"] = "OK"
            report["candidate_count"] = 0
            report["error"] = "No new reports in window"
            return report

        # 4. Shape to Bronze schema
        ingest_ts = datetime.now(timezone.utc)
        bronze_df = to_bronze(pdf_filtered, dataset=ds_name, url=url, ingest_ts=ingest_ts, spark=spark)

        # 5. Locate contract code column
        contract_code_col = validate_contract_code_column(bronze_df, ds_name)

        # 6. Validate
        validate_bronze_df(bronze_df, ds_name, contract_code_col, target_year)

        candidate_count = bronze_df.count()
        report["candidate_count"] = candidate_count

        if pre_count > 0:
            target_df = spark.table(table)

            # 7. Detect revision conflicts
            conflict_count = detect_revision_conflicts(
                bronze_df, target_df, contract_code_col
            )
            report["conflict_count"] = conflict_count

            # 8. Anti-join for new rows
            new_df = anti_join_new_rows(bronze_df, target_df, None, contract_code_col)
        else:
            # No existing table — all rows are new, just deduplicate
            full_key = ["source_dataset", contract_code_col, "report_date"]
            new_df = bronze_df.dropDuplicates(full_key)
            report["conflict_count"] = 0

        new_count = new_df.count()
        report["new_count"] = new_count
        report["duplicate_count"] = candidate_count - new_count - report["conflict_count"]

        if dry_run:
            report["status"] = "DRY_RUN"
            return report

        # 9. Write — append only new rows
        if new_count > 0:
            # Ensure table exists via DDL (never overwrite)
            if not spark.catalog.tableExists(table):
                cols_ddl = ", ".join(
                    f"`{f.name}` {f.dataType.simpleString()}" for f in new_df.schema.fields
                )
                spark.sql(
                    f"CREATE TABLE IF NOT EXISTS {table} ({cols_ddl}) USING DELTA"
                )

            new_df.write.format("delta").mode("append").option("mergeSchema", "true") \
                .saveAsTable(table)

        # 10. Verify and set status
        post_count, post_max_date = get_target_stats(spark, table)
        report["post_count"] = post_count
        report["post_max_date"] = str(post_max_date) if post_max_date else "N/A"

        if post_count - pre_count != new_count:
            report["status"] = "FAILED"
            report["error"] = (
                f"Count mismatch: post_count({post_count}) - pre_count({pre_count}) "
                f"!= new_count({new_count})"
            )
            return report

        # Verify no duplicate keys in target
        if post_count > 0:
            target_df_check = spark.table(table)
            full_key = ["source_dataset", contract_code_col, "report_date"]
            dup_count = (
                target_df_check.groupBy(*full_key)
                .count()
                .filter(F.col("count") > 1)
                .count()
            )
            if dup_count > 0:
                report["status"] = "FAILED"
                report["error"] = f"Duplicate keys found in target: {dup_count}"
                return report

        report["status"] = "OK"

    except Exception as e:
        report["status"] = "FAILED"
        report["error"] = str(e)

    return report


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="CFTC TFF Bronze Refresh — append-only incremental"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Discovery and counts only; no writes")
    mode.add_argument("--write", action="store_true", help="Append new rows to Bronze tables")

    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Override start date (default: MAX(report_date) + 1 day per table)",
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=DEFAULT_END_DATE,
        help=f"End date inclusive (default: {DEFAULT_END_DATE})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    dry_run = args.dry_run
    end_date = args.end_date

    _ensure_spark_imports()
    spark = SparkSession.builder.serverless(True).getOrCreate()
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_SCHEMA}")

    mode_label = "DRY-RUN" if dry_run else "WRITE"
    print(f"\n{'='*70}")
    print(f"CFTC TFF BRONZE REFRESH — {mode_label}")
    print(f"End date: {end_date}")
    print(f"{'='*70}\n")

    all_reports = []

    for ds in DATASETS:
        table = ds["table"]
        table_short = table.split(".")[-1]

        # Derive start date from target max
        if args.start_date:
            start_date = args.start_date
        else:
            _, pre_max = get_target_stats(spark, table)
            if pre_max is not None:
                start_date = pre_max + timedelta(days=1)
            else:
                start_date = date(TARGET_YEAR, 1, 1)

        print(f"\n--- {ds['name'].upper()} -> {table_short} ---")
        print(f"    Window: {start_date} <= report_date <= {end_date}")

        report = refresh_dataset(
            spark=spark,
            ds=ds,
            start_date=start_date,
            end_date=end_date,
            dry_run=dry_run,
            target_year=TARGET_YEAR,
        )
        all_reports.append(report)

        # Print per-dataset report
        print(f"    Status:        {report['status']}")
        print(f"    Pre-count:     {report['pre_count']}")
        print(f"    Pre-max-date:  {report['pre_max_date']}")
        print(f"    Candidates:    {report['candidate_count']}")
        print(f"    Conflicts:     {report['conflict_count']}")
        print(f"    Duplicates:    {report['duplicate_count']}")
        print(f"    New rows:      {report['new_count']}")
        if not dry_run:
            print(f"    Post-count:    {report['post_count']}")
            print(f"    Post-max-date: {report['post_max_date']}")
        if report["error"]:
            print(f"    Note/Error:    {report['error']}")
        if report["source_file"]:
            print(f"    Source:        {report['source_file']}")

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY ({mode_label})")
    print(f"{'='*70}")
    for r in all_reports:
        status_icon = "OK" if r["status"] in ("OK", "DRY_RUN") else "FAIL" if r["status"] == "FAILED" else "SKIP"
        print(f"  [{status_icon}] {r['dataset']:>10}  candidates={r['candidate_count']}  "
              f"new={r['new_count']}  conflicts={r['conflict_count']}  status={r['status']}")

    # Fail propagation: if any dataset failed, exit non-zero
    any_failed = any(r["status"] == "FAILED" for r in all_reports)
    if any_failed:
        print("\nOne or more datasets FAILED. Exiting with error.")
        sys.exit(1)

    print(f"\nCFTC TFF refresh complete ({mode_label}).")


if __name__ == "__main__":
    main()