"""notebooks/refresh_bronze_corporate_actions.py — Databricks notebook entry point.

Append-only refresh of ``bronze_corporate_actions`` from the live Gold
universe + SPY/RSP/QQQ using the Massive adapter in
``etl/corporate_actions.py``.

Import-safe: pure helpers at module scope, all Spark / network setup inside
``main()``.  ``if __name__ == "__main__": main()``.

Dual mode:
- Notebook / notebook-job (dbutils present): reads params from widgets,
  ignores sys.argv entirely (kernel-injected flags like ``-f`` would break
  argparse).
- CLI / spark_python_task (no dbutils): strict argparse, parse-before-Spark.

Source: Massive REST API only (source='massive').  API key read from
Databricks secret scope ``evangoh_capstone``/``massive_s3_secret_key``
(notebook mode) or env var ``MASSIVE_API_KEY`` (CLI mode).

Deduplication: one row per (symbol, ex_date) — latest fetched_ts wins.
Back-adjusted (split-only, not dividends): historical levels change when a
later split is loaded; returns are unaffected.  PIT consumers must use
returns, not historical adjusted levels.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
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

VALID_SOURCES = {"massive"}
VALID_MODES = {"dry-run", "write"}

MIN_DELAY_SECONDS = 0.5

_APIKEY_RE = re.compile(r"(apiKey=)[^&\s]+")


def _redact_api_key(text: str) -> str:
    """Redact apiKey values in text for safe logging."""
    return _APIKEY_RE.sub(r"\g<1>***REDACTED***", text)

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



def _resolve_cli_api_key() -> str:
    """CLI-mode Massive key: MASSIVE_API_KEY (plaintext) or the Databricks secret via the SDK.

    ``WorkspaceClient().secrets.get_secret(...).value`` is BASE64-encoded (unlike ``dbutils.secrets.get``,
    which returns plaintext), so it must be decoded before use or every request returns 401.
    """
    key = os.environ.get("MASSIVE_API_KEY", "")
    if key:
        return key
    try:
        from databricks.sdk import WorkspaceClient
        raw = WorkspaceClient().secrets.get_secret("evangoh_capstone", "massive_s3_secret_key").value
    except Exception:
        return ""
    if not raw:
        return ""
    return base64.b64decode(raw).decode("utf-8").strip()

def _make_adapter(source: str, delay_seconds: float, max_retries: int, api_key: str = ""):
    """Create the appropriate adapter instance."""
    if source == "massive":
        from etl.corporate_actions import MassiveCorporateActionsSource
        return MassiveCorporateActionsSource(
            api_key=api_key,
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
# Abstract interfaces for injectable dependencies
# ---------------------------------------------------------------------------

class Writer:
    """Abstract writer: appends rows to a table."""

    def append_rows(self, rows: list[dict], table_fqn: str) -> None:
        raise NotImplementedError


class CheckpointStore:
    """Abstract checkpoint store: logs symbol status."""

    def log(self, run_id: str, symbol: str, source: str, status: str,
            raw_count: int, deduped_count: int, error: str = "") -> None:
        raise NotImplementedError

    def completed_symbols(self, run_id: str) -> set[str]:
        raise NotImplementedError


class KeyVerifier:
    """Abstract key verifier: checks which keys exist in a table."""

    def verify_keys(self, keys: set[tuple], table_fqn: str) -> set[tuple]:
        """Return the subset of keys that exist in the table."""
        raise NotImplementedError


class SparkWriter(Writer):
    """Spark-based writer for production use."""

    def __init__(self, spark):
        self._spark = spark

    def append_rows(self, rows: list[dict], table_fqn: str) -> None:
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
        spark_rows = []
        for r in rows:
            spark_rows.append(Row(
                symbol=r["symbol"],
                ex_date=dt.date.fromisoformat(r["ex_date"]),
                split_ratio=r["split_ratio"],
                source=r["source"],
                fetched_ts=dt.datetime.fromisoformat(r["fetched_ts"]),
                information_available_ts=dt.datetime.fromisoformat(r["information_available_ts"]),
            ))
        df = self._spark.createDataFrame(spark_rows, schema=schema)
        df.write.format("delta").mode("append").saveAsTable(table_fqn)


class SparkCheckpointStore(CheckpointStore):
    """Spark-based checkpoint store for production use."""

    def __init__(self, spark):
        self._spark = spark

    def log(self, run_id: str, symbol: str, source: str, status: str,
            raw_count: int, deduped_count: int, error: str = "") -> None:
        _log_checkpoint(self._spark, run_id, symbol, source, status,
                        raw_count, deduped_count, error)

    def completed_symbols(self, run_id: str) -> set[str]:
        try:
            log_rows = self._spark.sql(
                f"SELECT DISTINCT symbol FROM {CHECKPOINT_TABLE} "
                f"WHERE run_id = '{run_id}' AND status IN ('SUCCESS', 'EMPTY')"
            ).collect()
            return {r["symbol"] for r in log_rows}
        except Exception:
            return set()


class SparkKeyVerifier(KeyVerifier):
    """Spark-based key verifier using DataFrame join (no SQL interpolation)."""

    def __init__(self, spark):
        self._spark = spark

    def verify_keys(self, keys: set[tuple], table_fqn: str) -> set[tuple]:
        if not keys:
            return set()
        try:
            from pyspark.sql import Row
            from pyspark.sql.types import (
                StructType, StructField, StringType, DateType,
            )
            schema = StructType([
                StructField("symbol", StringType(), False),
                StructField("ex_date", DateType(), False),
                StructField("source", StringType(), False),
            ])
            key_rows = [
                Row(symbol=k[0], ex_date=dt.date.fromisoformat(k[1]), source=k[2])
                for k in keys
            ]
            keys_df = self._spark.createDataFrame(key_rows, schema=schema)
            bronze_df = self._spark.sql(
                f"SELECT symbol, ex_date, source FROM {table_fqn}"
            )
            joined = keys_df.join(bronze_df, on=["symbol", "ex_date", "source"], how="inner")
            verified = joined.collect()
            return {(r["symbol"], r["ex_date"].isoformat(), r["source"]) for r in verified}
        except Exception as exc:
            print(f"  WARN: post-append verification query failed: {exc}")
            return set()


# ---------------------------------------------------------------------------
# Core batch processing (importable, testable)
# ---------------------------------------------------------------------------

def run_batch(
    symbols: list[str],
    adapter,
    writer: Writer,
    checkpoint_store: CheckpointStore,
    key_verifier: KeyVerifier,
    run_id: str,
    existing_keys_set: set[tuple],
    mode: str = "write",
    report: dict | None = None,
) -> tuple[list[dict], dict]:
    """Process a batch of symbols: fetch, validate, dedup, write, verify, checkpoint.

    Returns (new_rows_written, updated_report).
    """
    if report is None:
        report = {"attempted": 0, "success": 0, "empty": 0, "failed": 0,
                  "candidate_rows": 0, "deduped_rows": 0, "new_rows": 0,
                  "conflict_rows": 0, "failures": {}}

    completed_keys = checkpoint_store.completed_symbols(run_id) if mode == "write" else set()

    all_candidate_rows: list[dict] = []
    # Track successful fetches for deferred SUCCESS checkpointing
    successful_symbols: dict[str, tuple[int, int]] = {}

    for sym in symbols:
        if sym in completed_keys:
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
                    checkpoint_store.log(run_id, sym, "massive", "EMPTY", 0, 0)
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

            # Defer SUCCESS checkpoint — only after append + key verification
            successful_symbols[sym] = (len(valid_rows), len(deduped))

        except Exception as exc:
            report["failed"] += 1
            safe_msg = _redact_api_key(str(exc))[:200]
            report["failures"][sym] = safe_msg
            print(f"  FAILED {sym}: {safe_msg}")
            if mode == "write":
                checkpoint_store.log(run_id, sym, "massive", "FAILED", 0, 0, error=safe_msg)

    # --- Anti-join: filter out existing keys ---
    new_rows = [r for r in all_candidate_rows if _row_to_key(r) not in existing_keys_set]
    conflicts = [r for r in all_candidate_rows if _row_to_key(r) in existing_keys_set]
    report["new_rows"] = len(new_rows)
    report["conflict_rows"] = len(conflicts)

    # --- Write (write mode only) ---
    if mode == "write" and new_rows:
        try:
            writer.append_rows(new_rows, BRONZE_TABLE)
            print(f"  Appended {len(new_rows)} rows to {BRONZE_TABLE}")
        except Exception as exc:
            # Write failed — log all successful symbols as FAILED
            safe_msg = _redact_api_key(str(exc))[:200]
            for sym, (raw_cnt, dedup_cnt) in successful_symbols.items():
                checkpoint_store.log(run_id, sym, "massive", "FAILED",
                                     raw_cnt, dedup_cnt,
                                     error=f"write failed: {safe_msg}")
            return [], report

    # --- Post-append key verification via DataFrame join ---
    # Verify ALL candidate keys for each successful symbol — both newly
    # written and already-existing (conflict) keys.  This ensures that on
    # resume, a symbol whose rows already exist in bronze is verified and
    # checkpointed as SUCCESS instead of being re-fetched every time.
    if mode == "write" and successful_symbols:
        all_candidate_keys = {_row_to_key(r) for r in all_candidate_rows}
        verified_keys = key_verifier.verify_keys(all_candidate_keys, BRONZE_TABLE)

        # Group candidate rows by symbol
        keys_by_symbol: dict[str, set[tuple]] = {}
        for r in all_candidate_rows:
            sym = r["symbol"]
            k = _row_to_key(r)
            keys_by_symbol.setdefault(sym, set()).add(k)

        # Checkpoint SUCCESS only if ALL of a symbol's keys are verified
        for sym, (raw_cnt, dedup_cnt) in successful_symbols.items():
            if sym not in keys_by_symbol:
                continue
            sym_keys = keys_by_symbol[sym]
            if all(k in verified_keys for k in sym_keys):
                checkpoint_store.log(run_id, sym, "massive", "SUCCESS",
                                     raw_cnt, dedup_cnt)
            else:
                # Keys not all verified — log as FAILED so resume retries
                checkpoint_store.log(run_id, sym, "massive", "FAILED",
                                     raw_cnt, dedup_cnt,
                                     error="post-append key verification failed")

    return new_rows, report


# ---------------------------------------------------------------------------
# Notebook main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point — all Spark/dbutils/network setup lives here."""
    # --- Detect notebook context BEFORE any argument parsing ---
    dbutils_obj = globals().get("dbutils")

    # Defaults
    mode = "dry-run"
    source = "massive"
    symbol_start = ""
    symbol_end = ""
    delay_seconds = 0.5
    max_retries = 2
    run_id = _new_run_id()

    if dbutils_obj is not None:
        # ---- Notebook / notebook-job path ----
        # Declare widgets with defaults; Databricks injects overrides.
        # IGNORE sys.argv entirely — kernel-injected flags like -f would
        # cause argparse to exit 2.
        _widget_defaults = {
            "mode": mode,
            "source": source,
            "symbol_start": symbol_start,
            "symbol_end": symbol_end,
            "delay_seconds": str(delay_seconds),
            "max_retries": str(max_retries),
            "run_id": run_id,
        }
        for name, default in _widget_defaults.items():
            try:
                dbutils_obj.widgets.text(name, default)
            except Exception:
                pass  # widget may already exist

        mode = dbutils_obj.widgets.get("mode")
        source = dbutils_obj.widgets.get("source")
        symbol_start = dbutils_obj.widgets.get("symbol_start")
        symbol_end = dbutils_obj.widgets.get("symbol_end")
        try:
            delay_seconds = float(dbutils_obj.widgets.get("delay_seconds"))
        except (TypeError, ValueError):
            pass
        try:
            max_retries = int(dbutils_obj.widgets.get("max_retries"))
        except (TypeError, ValueError):
            pass
        run_id = dbutils_obj.widgets.get("run_id")
    else:
        # ---- CLI / spark_python_task path ----
        parser = argparse.ArgumentParser(
            description="Refresh bronze corporate actions from live universe.",
            allow_abbrev=False,
        )
        parser.add_argument("--mode", default=None, help="dry-run or write")
        parser.add_argument("--source", default=None, help="Data source (massive)")
        parser.add_argument("--symbol-start", default=None, help="Inclusive lower bound for symbol range")
        parser.add_argument("--symbol-end", default=None, help="Inclusive upper bound for symbol range")
        parser.add_argument("--delay-seconds", type=float, default=None, help="Min delay between fetches")
        parser.add_argument("--max-retries", type=int, default=None, help="Max retries per symbol")
        parser.add_argument("--run-id", default=None, help="Resume run id")
        # parse_args before Spark so --help and bad flags fail fast
        args = parser.parse_args()

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

    # --- Validate (both paths converge here) ---
    mode = _valid_mode(mode)
    source = _valid_source(source)
    delay_seconds = max(delay_seconds, MIN_DELAY_SECONDS)

    # --- Read Massive API key (required) ---
    massive_api_key = ""
    if dbutils_obj is not None:
        # Notebook mode: read from Databricks secret scope
        try:
            massive_api_key = dbutils_obj.secrets.get(
                "evangoh_capstone", "massive_s3_secret_key"
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to read Massive API key from Databricks secret "
                "scope 'evangoh_capstone' key 'massive_s3_secret_key'"
            ) from exc
    else:
        # CLI mode: env var or Databricks SDK
        massive_api_key = _resolve_cli_api_key()
        if not massive_api_key:
            raise RuntimeError(
                "Massive API key required: set MASSIVE_API_KEY env var "
                "or configure Databricks SDK credentials"
            )

    # --- Spark (after argparse/widgets so --help and bad flags fail fast) ---
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
    except ImportError:
        spark = None

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
        if dbutils_obj is not None:
            dbutils_obj.notebook.exit(json.dumps(report, default=str))
        return

    # --- Adapter ---
    adapter = _make_adapter("massive", delay_seconds, max_retries, massive_api_key)

    # --- Checkpoint log: check for already-completed symbols ---
    completed_keys: set[str] = set()
    if mode == "write":
        try:
            log_rows = spark.sql(
                f"SELECT DISTINCT symbol FROM {CHECKPOINT_TABLE} "
                f"WHERE run_id = '{run_id}' AND status IN ('SUCCESS', 'EMPTY')"
            ).collect()
            completed_keys = {r["symbol"] for r in log_rows}
            report["resumed"] = len(completed_keys)
        except Exception:
            pass  # table may not exist yet

    # --- Pre-Bronze count ---
    try:
        pre_count = spark.sql(f"SELECT COUNT(*) AS c FROM {BRONZE_TABLE}").collect()[0]["c"]
        report["pre_bronze_count"] = pre_count
    except Exception:
        report["pre_bronze_count"] = 0

    # --- Load existing Bronze keys for anti-join ---
    existing_keys_set: set[tuple] = set()
    try:
        existing_rows = spark.sql(
            f"SELECT symbol, CAST(ex_date AS STRING) AS ex_date, source FROM {BRONZE_TABLE}"
        ).collect()
        existing_keys_set = {(r["symbol"], r["ex_date"], r["source"]) for r in existing_rows}
        report["existing_keys"] = len(existing_keys_set)
    except Exception:
        pass  # table may not exist yet

    # --- Create injectable dependencies ---
    writer = SparkWriter(spark)
    checkpoint_store = SparkCheckpointStore(spark)
    key_verifier = SparkKeyVerifier(spark)

    # --- Process batch ---
    new_rows, batch_report = run_batch(
        symbols=all_symbols,
        adapter=adapter,
        writer=writer,
        checkpoint_store=checkpoint_store,
        key_verifier=key_verifier,
        run_id=run_id,
        existing_keys_set=existing_keys_set,
        mode=mode,
        report=report,
    )

    # Merge batch report
    report.update(batch_report)

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
    if dbutils_obj is not None:
        dbutils_obj.notebook.exit(json.dumps(report, default=str))


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