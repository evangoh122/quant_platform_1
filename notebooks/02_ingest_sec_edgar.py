# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # 02 — Ingest SEC EDGAR Data (for RAG)
# MAGIC
# MAGIC **Thin wrapper** around `pipelines/sec_rag_ingest.py`.
# MAGIC The legacy 3 600-line implementation was removed in this commit;
# MAGIC see git history up to `d0d063f` for the original version.
# MAGIC
# MAGIC **Production ingestion** is handled by the `sec_rag_ingest` Lakeflow Job
# MAGIC (`resources/jobs.yml`), which runs `pipelines/sec_rag_ingest.py`.
# MAGIC See `docs/runbook.md` for operational instructions.
# MAGIC
# MAGIC **Writes to:** `bootcamp_students.evangoh_capstone.bronze_sec_filings_v2`
# MAGIC
# MAGIC **Widget parameters** mirror the pipeline CLI flags.

# COMMAND ----------

# DBTITLE 1,Run pipeline
import os
import sys

# Repo root on the workspace
repo_root = os.path.dirname(os.path.dirname(os.path.abspath("__file__")))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from pipelines.sec_rag_ingest import main  # noqa: E402


def _build_argv():
    """Build argv list from Databricks widget values (or globals().get('dbutils'))."""
    dbutils = globals().get("dbutils")
    argv: list[str] = []

    def _add(flag, widget_name, default=None):
        if dbutils is not None:
            try:
                val = dbutils.widgets.get(widget_name)
            except Exception:
                val = None
        else:
            val = None
        if val is None:
            val = default
        if val not in (None, ""):
            argv.extend([flag, str(val)])

    def _add_bool(flag, widget_name):
        if dbutils is not None:
            try:
                val = dbutils.widgets.get(widget_name)
            except Exception:
                val = None
        else:
            val = None
        if val and val.lower() in ("true", "1", "yes"):
            argv.append(flag)

    _add("--tickers", "tickers")
    _add("--start-date", "start_date", "2020-01-01")
    _add("--forms", "forms", "10-K,10-Q")
    _add_bool("--dry-run", "dry_run")
    _add_bool("--include-historical", "include_historical")
    _add("--run-id", "run_id")

    return argv


main(_build_argv())