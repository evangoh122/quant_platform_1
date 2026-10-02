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
    ("gold_ohlcv_features", "gold/01_gold_ohlcv_features.sql", "sql"),
    ("gold_options_features", "gold/02_gold_options_features.sql", "sql"),
    ("gold_sec_features", "gold/gold_sec_features.py", "py"),
    ("gold_cot_features", "gold/04_gold_cot_features.sql", "sql"),
    ("gold_model_features", "gold/05_gold_model_features.sql", "sql"),
]

TARGET_TABLES = [
    "silver_ohlcv", "silver_ohlcv_quarantine_batch", "silver_options_quotes",
    "silver_options_trades", "silver_sec_sections", "silver_sec_entities",
    "silver_cot_positions",
    "gold_ohlcv_features", "gold_options_features", "gold_sec_features",
    "gold_cot_features", "gold_model_features",
]

DATE_START = "1900-01-01"
DATE_END = "2100-01-01"


def get_spark() -> DatabricksSession:
    return DatabricksSession.builder.serverless(True).getOrCreate()


def register_universe(spark) -> list[str]:
    symbols = load_universe()
    df = spark.createDataFrame([(s,) for s in symbols], schema="symbol string")
    df.createOrReplaceTempView("universe")
    return symbols


def truncate_targets(spark):
    for t in TARGET_TABLES:
        try:
            spark.sql(f"TRUNCATE TABLE {FQN}.{t}")
            print(f"  truncated {t}")
        except Exception as e:
            print(f"  skip truncate {t}: {str(e)[:120]}")


def count(spark, table: str) -> int:
    return spark.sql(f"SELECT COUNT(*) FROM {FQN}.{table}").collect()[0][0]


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
        sql = sql_text.format(date_start=DATE_START, date_end=DATE_END)
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


def run_checks(spark):
    print("\n=== PIT / DQ checks ===")
    checks = [
        ("options info_ts non-null",
         f"SELECT COUNT(*) FROM {FQN}.gold_options_features WHERE information_available_ts IS NULL"),
        ("sec info_ts non-null",
         f"SELECT COUNT(*) FROM {FQN}.gold_sec_features WHERE information_available_ts IS NULL"),
        ("cot info_ts non-null",
         f"SELECT COUNT(*) FROM {FQN}.gold_cot_features WHERE information_available_ts IS NULL"),
        ("ohlcv info_ts == feature_ts",
         f"SELECT COUNT(*) FROM {FQN}.gold_ohlcv_features WHERE information_available_ts <> feature_ts"),
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["silver", "gold"], default=None)
    ap.add_argument("--truncate", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--counts", action="store_true")
    args = ap.parse_args()

    spark = get_spark()
    symbols = register_universe(spark)
    print(f"universe: {len(symbols)} symbols")

    if args.truncate:
        print("\n=== truncate targets ===")
        truncate_targets(spark)

    if args.check:
        run_checks(spark)
        return

    for name, path, kind in STEPS:
        layer = "gold" if name.startswith("gold") else "silver"
        if args.only and layer != args.only:
            continue
        if args.counts:
            continue
        run_step(spark, name, path, kind, symbols)

    print("\n=== final row counts ===")
    for t in TARGET_TABLES:
        try:
            print(f"  {t}: {count(spark, t)}")
        except Exception as e:
            print(f"  {t}: ERROR {str(e)[:120]}")


if __name__ == "__main__":
    main()
