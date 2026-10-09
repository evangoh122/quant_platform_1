"""
Guard test: ensure retired yfinance/duckdb.local-store modules are not reintroduced.

Runs in CI without pyspark. Validates:
(a) No tracked .py outside allowlist imports yfinance.
(b) The six deleted ETL modules do not exist.
(c) Ontology has no yfinance key and massive == "implemented".
(d) requirements*.txt have no yfinance line.
(e) Nothing outside allowlist imports db.database (the retired module).
"""
import os
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent

ALLOWLIST_IMPORT_YFINANCE = {
    "docs/archive",
    "notebooks/archive",
    "tests/test_no_retired_sources.py",
}

ALLOWLIST_IMPORT_DB_DATABASE = {
    "docs/archive",
    "notebooks/archive",
    "tests/test_no_retired_sources.py",
    "conftest.py",
}

DEAD_ETL_MODULES = [
    "etl/extract_yfinance.py",
    "etl/extract_cot.py",
    "etl/extract_edgar.py",
    "etl/extract_options.py",
    "etl/extract_polygon.py",
    "etl/extract_stocks.py",
]


def _in_allowlist(rel: str, allowlist: set[str]) -> bool:
    for prefix in allowlist:
        if rel == prefix or rel.startswith(prefix + os.sep):
            return True
    return False


def _py_files():
    """Yield all tracked .py files relative to repo root."""
    for p in REPO.rglob("*.py"):
        rel = str(p.relative_to(REPO))
        if rel.startswith(".git" + os.sep):
            continue
        yield rel


class TestNoRetiredSources:

    def test_no_yfinance_import_in_production_code(self):
        """(a) No tracked .py outside allowlist imports yfinance."""
        violations = []
        for rel in _py_files():
            if _in_allowlist(rel, ALLOWLIST_IMPORT_YFINANCE):
                continue
            try:
                text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "import yfinance" in line or "from yfinance" in line:
                    violations.append(f"{rel}:{i}: {line.strip()}")
        assert not violations, "yfinance imports found:\n" + "\n".join(violations)

    def test_dead_etl_modules_do_not_exist(self):
        """(b) The six deleted ETL modules must not exist."""
        for mod in DEAD_ETL_MODULES:
            assert not (REPO / mod).exists(), f"Dead module still present: {mod}"

    def test_ontology_has_no_yfinance_source(self):
        """(c) table_semantics.yaml has no yfinance key; massive == implemented."""
        yaml_path = REPO / "ontology" / "table_semantics.yaml"
        assert yaml_path.exists(), f"Missing {yaml_path}"
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

        ca = data["tables"]["bronze_corporate_actions"]
        sources = ca.get("sources", {})
        assert "yfinance" not in sources, "yfinance key found in bronze_corporate_actions.sources"
        assert sources.get("massive") == "implemented", (
            f"bronze_corporate_actions.sources.massive must be 'implemented', got {sources.get('massive')!r}"
        )

        # Walk entire YAML for any yfinance key
        def _walk(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    assert "yfinance" not in str(k).lower(), f"yfinance key at {path}.{k}"
                    _walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    _walk(item, f"{path}[{i}]")

        _walk(data)

    def test_requirements_no_yfinance(self):
        """(d) requirements*.txt have no yfinance line."""
        for req in REPO.glob("requirements*.txt"):
            for i, line in enumerate(req.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                assert "yfinance" not in line.lower(), f"{req.name}:{i}: {line.strip()}"

    def test_no_db_database_import_outside_allowlist(self):
        """(e) Nothing outside allowlist imports db.database (retired module).

        Test files that use pytest.importorskip("db.database") are allowed —
        they use DuckDB as a test-time SQL engine and will be skipped when
        db.database is absent.
        """
        violations = []
        for rel in _py_files():
            if _in_allowlist(rel, ALLOWLIST_IMPORT_DB_DATABASE):
                continue
            try:
                text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Allow test files that guard db.database with importorskip
            if rel.startswith("tests" + os.sep) and "importorskip(\"db.database\"" in text:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "from db.database" in line or "import db.database" in line:
                    violations.append(f"{rel}:{i}: {line.strip()}")
        assert not violations, "db.database imports found:\n" + "\n".join(violations)