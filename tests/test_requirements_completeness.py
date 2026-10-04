"""AST-scan test: every third-party import reachable from api/, agent/,
db/, config/ must be declared in requirements.txt.

Walks the entire AST (including function bodies) so deferred imports like
``from databricks import sql`` inside function bodies are also caught.
ibapi and pyspark are explicitly allowed to be absent since they are optional.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories to scan (relative to project root).
_SCAN_DIRS = ["api", "agent", "db", "config"]

# Map top-level import name → PyPI distribution name.
# Only entries whose import name differs from the distribution name need
# explicit mapping; the test also derives a best-guess distribution name
# from the import name so most packages are covered automatically.
_IMPORT_TO_DIST: dict[str, str] = {
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "edgar": "edgartools",
    "psycopg_pool": "psycopg-pool",
    "langchain_openai": "langchain-openai",
    "langchain_core": "langchain-core",
    "sentence_transformers": "sentence-transformers",
    "rank_bm25": "rank-bm25",
    "huggingface_hub": "huggingface-hub",
    "databricks": "databricks-sdk",
    "databricks.sql": "databricks-sql-connector",
}

# Imports that are allowed to be absent from requirements.txt (deferred
# by design — only imported inside function bodies, never at module scope
# in the scanned directories, but we list them defensively).
_DEFERRED_ALLOWED = {"ibapi", "pyspark", "pyspark.sql"}

# Standard-library modules — use sys.stdlib_module_names (Python ≥3.10)
# for completeness, augmented with sub-package prefixes that appear in
# import statements but aren't top-level module names.
_STDLIB_MODULES: set[str] = set(sys.stdlib_module_names) | {
    "__future__", "posixpath", "site",
}


def _is_local_module(name: str) -> bool:
    """Check if the import name matches a top-level directory in the project."""
    top = name.split(".")[0]
    return (_PROJECT_ROOT / top).is_dir()


def _parse_requirements() -> set[str]:
    """Parse requirements.txt and return the set of declared distribution names (lowercased)."""
    req_path = _PROJECT_ROOT / "requirements.txt"
    if not req_path.exists():
        return set()
    dists: set[str] = set()
    for line in req_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip version specifiers and extras: "psycopg[binary]>=3.1" → "psycopg"
        name = re.split(r"[><=\[;]", line)[0].strip().lower()
        if name:
            dists.add(name)
    return dists


def _scan_all_imports(dirs: list[str]) -> set[str]:
    """Walk Python files in *dirs* and collect ALL third-party imports,
    including those inside function bodies (deferred imports).

    For ``ImportFrom`` nodes, both the full dotted module name (e.g.
    ``databricks.sql``) and the top-level package (e.g. ``databricks``) are
    collected so that dotted mappings in ``_IMPORT_TO_DIST`` are reachable.
    Also adds ``module.name`` for each alias (e.g. ``from databricks import sql``
    → ``databricks.sql``).
    """
    imports: set[str] = set()
    for d in dirs:
        dpath = _PROJECT_ROOT / d
        if not dpath.is_dir():
            continue
        for py_file in dpath.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(), filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.level == 0:
                        imports.add(node.module)
                        imports.add(node.module.split(".")[0])
                        # Also add module.alias_name for each imported name
                        # e.g. from databricks import sql → databricks.sql
                        for alias in node.names:
                            full = f"{node.module}.{alias.name}"
                            imports.add(full)
                            imports.add(full.split(".")[0])
    return imports


def _import_to_dist(import_name: str) -> str:
    """Map an import name to its likely PyPI distribution name.

    For dotted imports (e.g. ``fastapi.middleware.cors``), checks the full name
    first, then each prefix, so sub-modules of mapped packages resolve correctly.
    """
    # Check full name first
    if import_name in _IMPORT_TO_DIST:
        return _IMPORT_TO_DIST[import_name]
    # Check each prefix (e.g. "fastapi.middleware.cors" → "fastapi")
    parts = import_name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in _IMPORT_TO_DIST:
            return _IMPORT_TO_DIST[prefix]
    # For dotted imports, the distribution is usually the top-level package
    # (e.g. "fastapi.staticfiles" → "fastapi", "langgraph.graph" → "langgraph")
    if len(parts) > 1:
        return parts[0].replace("_", "-")
    # Best guess: underscores → hyphens (common convention)
    return import_name.replace("_", "-")


def test_all_top_level_imports_declared_in_requirements():
    """Every third-party import (including deferred) must be declared in requirements.txt."""
    req_dists = _parse_requirements()
    assert req_dists, "requirements.txt is empty or missing"

    top_imports = _scan_all_imports(_SCAN_DIRS)

    missing: list[str] = []
    for imp in sorted(top_imports):
        # Skip standard library (check both full name and top-level package)
        if imp in _STDLIB_MODULES or imp.split(".")[0] in _STDLIB_MODULES:
            continue
        # Skip local packages
        if _is_local_module(imp):
            continue
        # Skip deferred-allowed (check top-level package too)
        if imp in _DEFERRED_ALLOWED or imp.split(".")[0] in _DEFERRED_ALLOWED:
            continue

        dist = _import_to_dist(imp)
        if dist not in req_dists:
            missing.append(f"{imp} → {dist}")

    assert not missing, (
        f"These imports are reachable at module scope but missing from "
        f"requirements.txt: {missing}"
    )