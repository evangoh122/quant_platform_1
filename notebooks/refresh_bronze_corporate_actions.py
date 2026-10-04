"""notebooks/refresh_bronze_corporate_actions.py — Databricks notebook entry point.

Append-only refresh of ``bronze_corporate_actions`` from the live Gold
universe + SPY/RSP/QQQ using the source-neutral adapter in
``etl/corporate_actions.py``.

Import-safe: pure helpers at module scope, all Spark / dbutils / network
setup inside ``main()``.  ``if __name__ == "__main__": main()``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time as _time
import uuid
from pathlib import Path
from typing import Any, Optional

# Ensure repo root is on sys.path so `etl` is importable from notebooks/.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Pure helpers (no Spark, no network)
# ---------------------------------------------------------------------------

CATALOG = os.getenv("CATALOG", "bootcamp_students")
SCHEMA = os.getenv("SCHEMA", "evangoh_capstone")
FQN = f"{CATALOG}.{SCHEMA}"
BRONZE_TABLE = f"{FQN}.bronze_corporate_actions"
CHECKPOINT_TABLE = f"{FQN}.corporate_actions_ingestion_log"

VALID_SOURCES = {"yfinance"}
VALID_MODES = {"dry-run", "write"}

MIN_DELAY_SECONDS = 0.5

# Required Bronze columns (natural key excludes fetched_ts).
KEY_COLUMNS = ("symbol", "ex_date", "source")
ALL_COLUMNS = (
    "symbol", "ex_date", "split_ratio", "source",
    "fetched_ts", "information_available_ts",
)


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _new_run_id() -> str:
    return f"run-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _valid_mode(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
    return mode


def _valid_source(source: str) -> str:
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")
    return source


def _make_adapter(source: str, delay_seconds: float, max_retries: int):
    """Create the appropriate adapter instance."""
    from etl.corporate_actions import YFinanceCorporateActionsSource
    if source == "yfinance":
        return YFinanceCorporateActionsSource(
            delay_seconds=delay_seconds,
            max_retries=max_retries,
        )
    raise ValueError(f"Unknown source: {source}")


def _split_to_row(split) -> dict:
    """Convert a CorporateActionSplit to a Bronze row dict."""
    return {
        "symbol": split.symbol,
        "ex_date": split.ex_date.isoformat(),
        "split_ratio": split.split_ratio,
        "source": split.source,
        "fetched_ts": split.fetched_ts.isoformat(timespec="microseconds"),
        "information_available_ts": split.information_available_ts.isoformat(timespec="microseconds"),
    }


def _row_to_key(row: dict) -> tuple:
    """Extract the natural key from a row dict."""
    return (row["symbol"], row["ex_date"], row["source"])


def _validate_row(row: dict) -> Optional[str]:
    """Return an error string if a row is invalid, else None."""
    if not row.get("symbol"):
        return "missing symbol"
    if not row.get("ex_date"):
        return "missing ex_date"
    ratio = row.get("split_ratio")
    if ratio is None or not _is_finite_positive_nonone(ratio):
        return f"invalid split_ratio: {ratio}"
    if not row.get("source"):
        return "missing source"
    if not row.get("fetched_ts"):
        return "missing fetched_ts"
    if not row.get("information_available_ts"):
        return "missing information_available_ts"
    return None


def _is_finite_positive_nonone(v: Any) -> bool:
    try:
        r = float(v)
        import math
        return math.isfinite(r) and r > 0 and r != 1.0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Notebook main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point — all Spark/dbutils/network setup lives here."""
    # --- Parameters: argparse first (CLI/job), BEFORE Spark ---
    parser = argparse.ArgumentParser(
        description="Refresh bronze corporate actions from live universe.",
        allow_abbrev=False,
    )
    parser.add_argument("--mode", default=None, help="dry-run or write")
    parser.add_argument("--source", default=None, help="Data source (yfinance)")
    parser.add_argument("--symbol-start", default=None, help="Inclusive lower bound for symbol range")
    parser.add_argument("--symbol-end", default=None, help="Inclusive upper bound for symbol range")
    parser.add_argument("--delay-seconds", type=float, default=None, help="Min delay between fetches")
    parser.add_argument("--max-retries", type=int, default=None, help="Max retries per symbol")
    parser.add_argument("--run-id", default=None, help="Resume run id")
    args = parser.parse_args()

    # --- Spark / dbutils (after argparse so --help and bad flags fail fast) ---
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
    except ImportError:
        spark = None

    try:
        import dbutils  # type: ignore[import-not-found]
    except ImportError:
        dbutils = None

    # Defaults
    mode = "dry-run"
    source = "yfinance"
    symbol_start = ""
    symbol_end = ""
    delay_seconds = 0.5
    max_retries = 2
    run_id = _new_run_id()

    # Argparse overrides defaults
    if args.mode is not None:
        mode = args.mode
    if args.source is not None:
        source = args.source
    if args.symbol_start is not None:
        symbol_start = args.symbol_start
    if args.symbol_end is not None:
        symbol_end = args.symbol_end
    if args.delay_seconds is not None:
        delay_seconds = args.delay_seconds
    if args.max_retries is not None:
        max_retries = args.max_retries
    if args.run_id is not None:
        run_id = args.run_id

    # Widgets override defaults only when argparse didn't supply a value
    if dbutils is not None:
        if args.mode is None:
            try:
                mode = dbutils.widgets.get("mode")
            except Exception:
                pass
        if args.source is None:
            try:
                source = dbutils.widgets.get("source")
            except Exception:
                pass
        if args.symbol_start is None:
            try:
                symbol_start = dbutils.widgets.get("symbol_start")
            except Exception:
                pass
        if args.symbol_end is None:
            try:
                symbol_end = dbutils.widgets.get("symbol_end")
            except Exception:
                pass
        if args.delay_seconds is None:
            try:
                delay_seconds = float(dbutils.widgets.get("delay_seconds"))
            except Exception:
                pass
        if args.max_retries is None:
            try:
                max_retries = int(dbutils.widgets.get("max_retries"))
            except Exception:
                pass
        if args.run_id is None:
            try:
                run_id = dbutils.widgets.get("run_id")
            except Exception:
                pass

    mode = _valid_mode(mode)
    source = _valid_source(source)
    delay_seconds = max(delay_seconds, MIN_DELAY_SECONDS)

    # --- Report accumulator ---
    report: dict[str, Any] = {
        "mode": mode,
        "run_id": run_id,
        "source": source,
        "symbol_start": symbol_start or None,
        "symbol_end": symbol_end or None,
        "delay_seconds": delay_seconds,
        "max_retries": max_retries,
        "universe_count": 0,
        "final_symbol_count": 0,
        "attempted": 0,
        "success": 0,
        "empty": 0,
        "failed": 0,
        "resumed": 0,
        "candidate_rows": 0,
        "deduped_rows": 0,
        "existing_keys": 0,
        "new_rows": 0,
        "conflict_rows": 0,
        "pre_bronze_count": 0,
        "post_bronze_count": 0,
        "failures": {},
        "start_time": _now_utc().isoformat(),
        "end_time": None,
        "duration_seconds": None,
        "effective_rate": None,
    }

    t0 = _time.time()

    # --- Universe query ---
    universe_sql = """
        SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
        FROM {fqn}.gold_tradable_universe
        WHERE symbol IS NOT NULL
        UNION SELECT 'SPY'
        UNION SELECT 'RSP'
        UNION SELECT 'QQQ'
    """.format(fqn=FQN)

    if spark is None:
        raise RuntimeError("Spark session required for universe query")

    universe_rows = spark.sql(universe_sql).collect()
    all_symbols = sorted({r["symbol"] for r in universe_rows if r["symbol"]})
    report["universe_count"] = len(universe_rows)
    report["final_symbol_count"] = len(all_symbols)

    # Apply symbol bounds
    if symbol_start:
        all_symbols = [s for s in all_symbols if s >= symbol_start]
    if symbol_end:
        all_symbols = [s for s in all_symbols if s <= symbol_end]

    print(f"Universe: {report['universe_count']} raw, "
          f"{report['final_symbol_count']} final, "
          f"{len(all_symbols)} in range")

    if not all_symbols:
        report["end_time"] = _now_utc().isoformat()
        report["duration_seconds"] = round(_time.time() - t0, 2)
        print(json.dumps(report, indent=2, default=str))
        if dbutils is not None:
            dbutils.notebook.exit(json.dumps(report, default=str))
        return

    # --- Adapter ---
    adapter = _make_adapter(source, delay_seconds, max_retries)

    # --- Checkpoint log: check for already-completed symbols ---
    completed_symbols: set[str] = set()
    if mode == "write":
        try:
            log_rows = spark.sql(
                f"SELECT DISTINCT symbol FROM {CHECKPOINT_TABLE} "
                f"WHERE run_id = '{run_id}' AND status IN ('SUCCESS', 'EMPTY')"
            ).collect()
            completed_symbols = {r["symbol"] for r in log_rows}
            report["resumed"] = len(completed_symbols)
        except Exception:
            pass  # table may not exist yet

    # --- Pre-Bronze count ---
    try:
        pre_count = spark.sql(f"SELECT COUNT(*) AS c FROM {BRONZE_TABLE}").collect()[0]["c"]
        report["pre_bronze_count"] = pre_count
    except Exception:
        report["pre_bronze_count"] = 0

    # --- Fetch loop ---
    all_candidate_rows: list[dict] = []
    existing_keys_set: set[tuple] = set()

    # Load existing Bronze keys for anti-join
    try:
        existing_rows = spark.sql(
            f"SELECT symbol, CAST(ex_date AS STRING) AS ex_date, source FROM {BRONZE_TABLE}"
        ).collect()
        existing_keys_set = {(r["symbol"], r["ex_date"], r["source"]) for r in existing_rows}
        report["existing_keys"] = len(existing_keys_set)
    except Exception:
        pass  # table may not exist yet

    for sym in all_symbols:
        if sym in completed_symbols:
            continue

        report["attempted"] += 1
        try:
            splits = adapter.fetch_splits(sym)
            rows = [_split_to_row(s) for s in splits]

            # Validate
            valid_rows = []
            for r in rows:
                err = _validate_row(r)
                if err:
                    print(f"  WARN {sym}: {err}")
                    continue
                valid_rows.append(r)

            if not valid_rows:
                report["empty"] += 1
                if mode == "write":
                    _log_checkpoint(spark, run_id, sym, source, "EMPTY", 0, 0)
                continue

            # Deduplicate within batch by natural key
            seen_keys: set[tuple] = set()
            deduped = []
            for r in valid_rows:
                k = _row_to_key(r)
                if k not in seen_keys:
                    seen_keys.add(k)
                    deduped.append(r)

            all_candidate_rows.extend(deduped)
            report["success"] += 1
            report["candidate_rows"] += len(valid_rows)
            report["deduped_rows"] += len(deduped)

            if mode == "write":
                _log_checkpoint(spark, run_id, sym, source, "SUCCESS",
                                len(valid_rows), len(deduped))

        except Exception as exc:
            report["failed"] += 1
            report["failures"][sym] = str(exc)[:200]
            print(f"  FAILED {sym}: {exc}")
            if mode == "write":
                _log_checkpoint(spark, run_id, sym, source, "FAILED", 0, 0,
                                error=str(exc)[:200])

        _time.sleep(delay_seconds)

    # --- Anti-join: filter out existing keys ---
    new_rows = [r for r in all_candidate_rows if _row_to_key(r) not in existing_keys_set]
    conflicts = [r for r in all_candidate_rows if _row_to_key(r) in existing_keys_set]
    report["new_rows"] = len(new_rows)
    report["conflict_rows"] = len(conflicts)

    # --- Write Bronze (write mode only) ---
    if mode == "write" and new_rows:
        from pyspark.sql import Row
        from pyspark.sql.types import (
            StructType, StructField, StringType, DoubleType, TimestampType, DateType,
        )

        schema = StructType([
            StructField("symbol", StringType(), False),
            StructField("ex_date", DateType(), False),
            StructField("split_ratio", DoubleType(), False),
            StructField("source", StringType(), False),
            StructField("fetched_ts", TimestampType(), False),
            StructField("information_available_ts", TimestampType(), False),
        ])

        # Convert row dicts to Spark Rows with proper types
        spark_rows = []
        for r in new_rows:
            spark_rows.append(Row(
                symbol=r["symbol"],
                ex_date=dt.date.fromisoformat(r["ex_date"]),
                split_ratio=r["split_ratio"],
                source=r["source"],
                fetched_ts=dt.datetime.fromisoformat(r["fetched_ts"]),
                information_available_ts=dt.datetime.fromisoformat(r["information_available_ts"]),
            ))

        df = spark.createDataFrame(spark_rows, schema=schema)
        df.write.format("delta").mode("append").saveAsTable(BRONZE_TABLE)
        print(f"  Appended {len(new_rows)} rows to {BRONZE_TABLE}")

    # --- Post-Bronze count ---
    try:
        post_count = spark.sql(f"SELECT COUNT(*) AS c FROM {BRONZE_TABLE}").collect()[0]["c"]
        report["post_bronze_count"] = post_count
    except Exception:
        report["post_bronze_count"] = report["pre_bronze_count"]

    # --- Finalize ---
    elapsed = _time.time() - t0
    report["end_time"] = _now_utc().isoformat()
    report["duration_seconds"] = round(elapsed, 2)
    if report["attempted"] > 0 and elapsed > 0:
        report["effective_rate"] = round(report["attempted"] / elapsed, 2)

    print(json.dumps(report, indent=2, default=str))
    if dbutils is not None:
        dbutils.notebook.exit(json.dumps(report, default=str))


def _log_checkpoint(
    spark,
    run_id: str,
    symbol: str,
    source: str,
    status: str,
    raw_count: int,
    deduped_count: int,
    error: str = "",
) -> None:
    """Append a checkpoint row to the operational log table."""
    try:
        from pyspark.sql import Row
        now = _now_utc()
        row = Row(
            run_id=run_id,
            symbol=symbol,
            source=source,
            status=status,
            attempts=1,
            started_ts=now,
            completed_ts=now,
            raw_count=raw_count,
            deduped_count=deduped_count,
            conflict_count=0,
            error_text=error,
        )
        df = spark.createDataFrame([row])
        df.write.format("delta").mode("append").saveAsTable(CHECKPOINT_TABLE)
    except Exception as exc:
        print(f"  WARN: failed to log checkpoint for {symbol}: {exc}")


if __name__ == "__main__":
    main()