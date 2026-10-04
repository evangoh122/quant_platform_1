"""pipelines/run_silver_gold.py — bronze -> silver -> gold orchestrator (Spark).

Reads the MVP universe from config/universe.yaml and registers it as a temp
view ``universe`` so every silver/gold transform filters symbols from that file
(no hardcoded ticker lists in transform code). Executes the version-controlled
transforms under silver/ and gold/ in dependency order via a serverless Spark
session (databricks-connect). Idempotent: every transform is a MERGE on a
stable key.

Usage:
    python pipelines/run_silver_gold.py --truncate        # clean full backfill
    python pipelines/run_silver_gold.py                   # idempotent re-run
    python pipelines/run_silver_gold.py --only silver
    python pipelines/run_silver_gold.py --only gold
    python pipelines/run_silver_gold.py --check           # PIT + DQ checks
    python pipelines/run_silver_gold.py --counts          # row counts only

Credentials come from ~/.databrickscfg (DATABRICKS_PROFILE, default evangohsg).
No secrets are stored in the repo.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from databricks.connect import DatabricksSession

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.universe import load_universe  # noqa: E402

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
FQN = f"{CATALOG}.{SCHEMA}"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (name, path, kind). Order matters (dependencies).
#   kind "sql" -> a .sql transform executed via spark.sql (universe temp view).
#   kind "py"  -> a Python module exposing build(spark, universe) -> row count.
STEPS = [
    ("silver_ohlcv", "silver/01_silver_ohlcv.sql", "sql"),
    ("silver_ohlcv_quarantine_batch", "silver/02_silver_ohlcv_quarantine.sql", "sql"),
    ("silver_options_quotes", "silver/03_silver_options_quotes.sql", "sql"),
    ("silver_options_trades", "silver/04_silver_options_trades.sql", "sql"),
    ("silver_sec_sections", "silver/05_silver_sec_sections.sql", "sql"),
    ("silver_sec_entities", "silver/06_silver_sec_entities.sql", "sql"),
    ("silver_cot_positions", "silver/07_silver_cot_positions.sql", "sql"),
    ("silver_ohlcv_day_adjusted", "silver/08_silver_ohlcv_day_adjusted.sql", "sql"),
    ("data_quality_breaks", "silver/08_silver_ohlcv_day_adjusted.sql", "sql"),
    ("gold_ohlcv_features", "gold/01_gold_ohlcv_features.sql", "sql"),
    ("gold_options_features", "gold/02_gold_options_features.sql", "sql"),
    ("gold_sec_features", "gold/gold_sec_features.py", "py"),
    ("gold_sec_coverage", "gold/07_gold_sec_coverage.sql", "sql"),
    ("gold_cot_features", "gold/04_gold_cot_features.sql", "sql"),
    ("gold_model_features", "gold/05_gold_model_features.sql", "sql"),
    ("gold_tradable_universe", "gold/06_gold_tradable_universe.sql", "sql"),
    ("gold_regime_features", "gold/07_gold_regime_features.sql", "sql"),
]

TARGET_TABLES = [
    "silver_ohlcv", "silver_ohlcv_quarantine_batch", "silver_options_quotes",
    "silver_options_trades", "silver_sec_sections", "silver_sec_entities",
    "silver_cot_positions", "silver_ohlcv_day_adjusted", "data_quality_breaks",
    "gold_ohlcv_features", "gold_options_features", "gold_sec_features",
    "gold_sec_coverage", "gold_cot_features", "gold_model_features",
    "gold_tradable_universe", "gold_regime_features",
]

DATE_START = "1900-01-01"
DATE_END = "2100-01-01"

# Round 8 additive schema change: gold_model_features retains each joined source
# row's information_available_ts in one *_available_ts column per source, so the
# matrix availability invariant can be checked exactly (no source back-join).
GOLD_MODEL_AVAILABILITY_COLUMNS = {
    "ohlcv_available_ts": "TIMESTAMP",
    "options_available_ts": "TIMESTAMP",
    "sec_available_ts": "TIMESTAMP",
    "cot_available_ts": "TIMESTAMP",
}


def get_spark() -> DatabricksSession:
    return DatabricksSession.builder.serverless(True).getOrCreate()


def register_universe(spark) -> list[str]:
    """Register the expanded SEC universe as a temp view.

    Combines gold_tradable_universe (all symbols ever traded) with the
    16 hardcoded SEC tickers, so silver transforms can ingest new tickers
    beyond the original MVP universe.
    """
    symbols = load_universe()
    df = spark.createDataFrame([(s,) for s in symbols], schema="symbol string")
    df.createOrReplaceTempView("universe")
    return symbols


_NO_TRUNCATE = {"data_quality_breaks"}  # preserves manual break reviews


def truncate_targets(spark):
    for t in TARGET_TABLES:
        if t in _NO_TRUNCATE:
            print(f"  skipped truncate {t} (preserves manual reviews)")
            continue
        try:
            spark.sql(f"TRUNCATE TABLE {FQN}.{t}")
            print(f"  truncated {t}")
        except Exception as e:
            print(f"  FAILED to truncate {t}: {str(e)[:200]}")
            raise


def count(spark, table: str) -> int:
    return spark.sql(f"SELECT COUNT(*) FROM {FQN}.{table}").collect()[0][0]


def ensure_model_availability_columns(spark):
    """Additive round-8 schema change on gold_model_features.

    Adds each missing *_available_ts column with ALTER TABLE ... ADD COLUMNS so
    the table retains the exact source row joined. Idempotent and re-runnable:
    only columns not already present are added. Requires the table to exist
    (it does — the build MERGEs into a pre-deployed table)."""
    try:
        existing = set(spark.table(f"{FQN}.gold_model_features").columns)
    except Exception as e:
        print(f"  ensure columns: gold_model_features not readable "
              f"({str(e)[:80]}); skipping")
        return
    missing = [c for c in GOLD_MODEL_AVAILABILITY_COLUMNS if c not in existing]
    if not missing:
        return
    cols = ", ".join(f"{c} {GOLD_MODEL_AVAILABILITY_COLUMNS[c]}" for c in missing)
    spark.sql(f"ALTER TABLE {FQN}.gold_model_features ADD COLUMNS ({cols})")
    print(f"  added gold_model_features columns: {', '.join(missing)}")


def run_step(spark, name, path, kind, symbols):
    print(f"\n=== {name} ===")
    t0 = time.time()
    if kind == "py":
        import importlib.util

        spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        n = mod.build(spark, symbols)
    else:
        sql_text = open(os.path.join(HERE, path), encoding="utf-8").read()
        sql = (sql_text
               .replace("{date_start}", DATE_START)
               .replace("{date_end}", DATE_END)
               .replace("{catalog}", CATALOG)
               .replace("{schema}", SCHEMA))
        for stmt in split_statements(sql):
            spark.sql(stmt)
        n = count(spark, name)
    print(f"  -> {name}: {n} rows ({time.time()-t0:.1f}s)")


def split_statements(sql: str) -> list[str]:
    """Strip comment lines, then split the remaining SQL into individual
    statements on ';'. Stripping comments first prevents ';' inside a comment
    from being treated as a statement boundary."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    out = []
    for part in body.split(";"):
        part = part.strip()
        if part:
            out.append(part)
    return out


def run_availability_invariant(spark):
    """Availability invariant: a daily/period feature must not become available
    before the end of the source window it aggregates.

    For daily options, a feature for day d must be available at/after the session
    close (16:00 America/New_York) of day d — not at the provider's start-of-day
    stamp. For COT, the release must be at/after the report week end. For minute
    OHLCV, a bar labelled [t, t+1min) is only known at t+1min, so
    information_available_ts must be >= event_ts + the bar interval. Raises
    RuntimeError (failing the build) on any violating row."""
    print("\n=== availability invariant ===")
    checks = [
        ("options info_ts >= session close",
         f"""SELECT COUNT(*) FROM {FQN}.gold_options_features
              WHERE information_available_ts < convert_timezone(
                  'America/New_York', 'UTC',
                  to_timestamp(concat(cast(DATE(feature_ts) AS STRING), ' 16:00:00')))"""),
        ("cot info_ts >= report_date",
         f"""SELECT COUNT(*) FROM {FQN}.gold_cot_features
              WHERE information_available_ts < CAST(report_date AS TIMESTAMP)"""),
        ("ohlcv minute info_ts >= event_ts + 1 minute",
         f"""SELECT COUNT(*) FROM {FQN}.gold_ohlcv_features
              WHERE information_available_ts < feature_ts + INTERVAL 1 MINUTE"""),
    ]
    violations = 0
    for label, sql in checks:
        v = spark.sql(sql).collect()[0][0]
        print(f"  {label}: {v} violating rows")
        violations += int(v)
    if violations:
        raise RuntimeError(
            f"availability invariant violated: {violations} row(s) "
            f"are available before the end of their source window"
        )
    return violations


def run_matrix_invariant(spark):
    """Matrix-level availability invariant (round 8): exact and cheap.

    gold_model_features now retains the information_available_ts of the exact
    source row joined, in ohlcv_available_ts / options_available_ts /
    sec_available_ts / cot_available_ts. Two properties must hold for every
    matrix row:

      1. GREATEST(all non-null *_available_ts) <= prediction_ts — no joined
         source feature became available after the prediction timestamp.
      2. A source's features are non-NULL only if its *_available_ts is
         non-NULL — the availability stamp is retained exactly when the source
         contributed.

    Property (1) alone is insufficient: GREATEST silently ignores NULL
    availability columns, so a row that lost its stamp would pass. Property (2)
    closes that gap by tying populated features to a retained stamp. Raises
    RuntimeError on any violating row."""
    print("\n=== matrix availability invariant ===")
    epoch = "to_timestamp('1900-01-01 00:00:00')"
    checks = [
        ("all source availability <= prediction_ts",
         f"""SELECT COUNT(*) FROM {FQN}.gold_model_features
             WHERE GREATEST(
                     ohlcv_available_ts,
                     COALESCE(options_available_ts, {epoch}),
                     COALESCE(sec_available_ts, {epoch}),
                     COALESCE(cot_available_ts, {epoch})
                   ) > prediction_ts"""),
        ("ohlcv features imply ohlcv_available_ts",
         f"""SELECT COUNT(*) FROM {FQN}.gold_model_features
             WHERE ohlcv_available_ts IS NULL
               AND (return_1m IS NOT NULL OR return_5m IS NOT NULL
                    OR return_15m IS NOT NULL OR return_30m IS NOT NULL
                    OR rvol_5m IS NOT NULL OR rvol_15m IS NOT NULL
                    OR rvol_30m IS NOT NULL OR atr_14 IS NOT NULL
                    OR rsi_14 IS NOT NULL OR vwap_deviation IS NOT NULL
                    OR relative_volume IS NOT NULL)"""),
        ("options features imply options_available_ts",
         f"""SELECT COUNT(*) FROM {FQN}.gold_model_features
             WHERE options_available_ts IS NULL
               AND (put_call_ratio IS NOT NULL
                    OR iv_atm IS NOT NULL
                    OR iv_skew IS NOT NULL
                    OR iv_term_slope IS NOT NULL
                    OR volume_anomaly_zscore IS NOT NULL)"""),
        ("sec features imply sec_available_ts",
         f"""SELECT COUNT(*) FROM {FQN}.gold_model_features
             WHERE sec_available_ts IS NULL
               AND (sec_sentiment_score IS NOT NULL
                    OR sec_risk_factor_change IS NOT NULL
                    OR sec_material_event IS NOT NULL)"""),
        ("cot features imply cot_available_ts",
         f"""SELECT COUNT(*) FROM {FQN}.gold_model_features
             WHERE cot_available_ts IS NULL
               AND (cot_lev_money_zscore IS NOT NULL
                    OR cot_crowding_score IS NOT NULL
                    OR cot_regime_label IS NOT NULL)"""),
    ]
    violations = 0
    for label, sql in checks:
        v = spark.sql(sql).collect()[0][0]
        print(f"  {label}: {v} violating rows")
        violations += int(v)
    if violations:
        raise RuntimeError(
            f"matrix availability invariant violated: {violations} row(s) "
            f"have a source feature whose availability is not retained or "
            f"is after prediction_ts"
        )
    return violations


def run_checks(spark):
    print("\n=== PIT / DQ checks ===")
    checks = [
        ("options info_ts non-null",
         f"SELECT COUNT(*) FROM {FQN}.gold_options_features WHERE information_available_ts IS NULL"),
        ("sec info_ts non-null",
         f"SELECT COUNT(*) FROM {FQN}.gold_sec_features WHERE information_available_ts IS NULL"),
        ("cot info_ts non-null",
         f"SELECT COUNT(*) FROM {FQN}.gold_cot_features WHERE information_available_ts IS NULL"),
        ("ohlcv info_ts == feature_ts + 1 minute",
         f"SELECT COUNT(*) FROM {FQN}.gold_ohlcv_features WHERE information_available_ts <> feature_ts + INTERVAL 1 MINUTE"),
        ("gold_model_features null snapshot_id",
         f"SELECT COUNT(*) FROM {FQN}.gold_model_features WHERE feature_snapshot_id IS NULL"),
        ("silver_ohlcv range violations",
         f"SELECT COUNT(*) FROM {FQN}.silver_ohlcv WHERE high < GREATEST(open, close) OR low > LEAST(open, close) OR volume < 0"),
        ("silver_ohlcv null prices",
         f"SELECT COUNT(*) FROM {FQN}.silver_ohlcv WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL"),
        ("silver_cot_positions null market_code",
         f"SELECT COUNT(*) FROM {FQN}.silver_cot_positions WHERE market_code IS NULL"),
    ]
    for label, sql in checks:
        v = spark.sql(sql).collect()[0][0]
        print(f"  {label}: {v}")

    # --- Corporate-action checks ---
    ca_checks = [
        ("bronze_corporate_actions duplicate keys",
         f"""SELECT COUNT(*) FROM (
               SELECT symbol, CAST(ex_date AS STRING) AS ex_date, source, COUNT(*) AS cnt
               FROM {FQN}.bronze_corporate_actions
               GROUP BY symbol, CAST(ex_date AS STRING), source HAVING cnt > 1
             )"""),
        ("silver_ohlcv_day_adjusted duplicate keys",
         f"""SELECT COUNT(*) FROM (
               SELECT symbol, event_date, COUNT(*) AS cnt
               FROM {FQN}.silver_ohlcv_day_adjusted
               GROUP BY symbol, event_date HAVING cnt > 1
             )"""),
        ("data_quality_breaks duplicate keys",
         f"""SELECT COUNT(*) FROM (
               SELECT symbol, event_date, COUNT(*) AS cnt
               FROM {FQN}.data_quality_breaks
               GROUP BY symbol, event_date HAVING cnt > 1
             )"""),
        ("adjusted nonpositive split_ratio",
         f"SELECT COUNT(*) FROM {FQN}.bronze_corporate_actions WHERE split_ratio <= 0 OR split_ratio IS NULL"),
        ("adjusted nonfinite factors",
         f"""SELECT COUNT(*) FROM {FQN}.silver_ohlcv_day_adjusted
              WHERE cumulative_split_ratio <= 0 OR price_adjustment_factor <= 0
                 OR cumulative_split_ratio IS NULL OR price_adjustment_factor IS NULL"""),
        ("adjusted nonpositive prices",
         f"""SELECT COUNT(*) FROM {FQN}.silver_ohlcv_day_adjusted
              WHERE adj_close <= 0 OR adj_close IS NULL"""),
        ("factor product != 1",
         f"""SELECT COUNT(*) FROM {FQN}.silver_ohlcv_day_adjusted
              WHERE ABS(price_adjustment_factor * cumulative_split_ratio - 1.0) > 0.001"""),
        ("explained rows with split_error > 0.03",
         f"""SELECT COUNT(*) FROM {FQN}.data_quality_breaks
              WHERE classification = 'SPLIT_EXPLAINED' AND split_error > 0.03"""),
        ("masked rows with return_1d NOT NULL",
         f"""SELECT COUNT(*) FROM {FQN}.silver_ohlcv_day_adjusted
              WHERE is_data_quality_break = TRUE AND return_1d IS NOT NULL"""),
        ("masked return filled with zero",
         f"""SELECT COUNT(*) FROM {FQN}.silver_ohlcv_day_adjusted
              WHERE is_data_quality_break = TRUE AND return_1d = 0.0"""),
    ]
    if ca_checks:
        print("\n=== corporate-action checks ===")
        for label, sql in ca_checks:
            try:
                v = spark.sql(sql).collect()[0][0]
                print(f"  {label}: {v}")
            except Exception as e:
                print(f"  {label}: ERROR {str(e)[:120]}")

    run_availability_invariant(spark)
    run_matrix_invariant(spark)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["silver", "gold"], default=None)
    ap.add_argument("--truncate", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--schema", default=None,
                    help="Target schema (overrides the SCHEMA env var); set per bundle target")
    args = ap.parse_args()
    if args.schema:
        global SCHEMA, FQN
        SCHEMA = args.schema
        FQN = f"{CATALOG}.{SCHEMA}"

    spark = get_spark()
    symbols = register_universe(spark)
    print(f"universe: {len(symbols)} symbols")

    if args.truncate:
        print("\n=== truncate targets ===")
        truncate_targets(spark)

    if args.check:
        run_checks(spark)
        return

    if not args.counts and (args.only is None or args.only == "gold"):
        ensure_model_availability_columns(spark)

    for name, path, kind in STEPS:
        layer = "gold" if name.startswith("gold") else "silver"
        if args.only and layer != args.only:
            continue
        if args.counts:
            continue
        run_step(spark, name, path, kind, symbols)

    if not args.counts and (args.only is None or args.only == "gold"):
        run_availability_invariant(spark)
        run_matrix_invariant(spark)

    print("\n=== final row counts ===")
    for t in TARGET_TABLES:
        try:
            print(f"  {t}: {count(spark, t)}")
        except Exception as e:
            print(f"  {t}: ERROR {str(e)[:120]}")


if __name__ == "__main__":
    main()
