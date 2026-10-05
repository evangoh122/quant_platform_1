"""pipelines/_runtime.py — Shared serverless-compatible runtime helpers.

Every ``python_file`` entry point referenced by ``resources/jobs.yml`` should
import :func:`repo_root` and :func:`get_spark` from this module instead of
rolling its own ``__file__`` / ``DatabricksSession`` logic.

Design constraints
------------------
* **Serverless spark_python_task** does not define ``__file__``; ``sys.argv[0]``
  is the script path in that environment.
* **Local / notebook execution** has ``__file__`` set normally.
* Inside a Databricks job (``DATABRICKS_RUNTIME_VERSION`` is set) the ambient
  ``SparkSession`` must be used — creating a ``DatabricksSession`` conflicts
  with the runtime-managed session.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    """Return the repository root as an absolute ``Path``.

    Robust in serverless ``spark_python_task`` where ``__file__`` is not set:
    falls back to ``sys.argv[0]``.  Both resolve to the *script* path, and the
    repo root is two parents up from ``pipelines/*.py`` (or ``ml/*.py``, etc.).
    """
    script = globals().get("__file__") or sys.argv[0]
    return Path(script).resolve().parent.parent


def get_spark():
    """Return a ``SparkSession`` suitable for the current execution context.

    * If ``DATABRICKS_RUNTIME_VERSION`` is set (i.e. running inside a Databricks
      job, including serverless), return the ambient session via
      ``SparkSession.builder.getOrCreate()``.
    * Otherwise (local development with databricks-connect), create a
      ``DatabricksSession`` in serverless mode.
    """
    if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    from databricks.connect import DatabricksSession
    return DatabricksSession.builder.serverless(True).getOrCreate()