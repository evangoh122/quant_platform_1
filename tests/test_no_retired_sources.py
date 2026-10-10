"""
Guard test: ensure retired yfinance/duckdb.local-store modules are not reintroduced.

Runs in CI without pyspark. Validates:
(a) No tracked .py outside allowlist imports yfinance.
(b) The six deleted ETL modules do not exist.
(c) Ontology has no yfinance key and massive == "implemented".
(d) requirements*.txt have no yfinance line.
(e) Nothing outside allowlist imports db.database (the retired module).
(f) No pytest fixture named tmp_db or db_conn under conftest.py/tests/.
"""
import ast
import os
import re
import subprocess
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
    norm_rel = rel.replace(os.sep, "/")
    for prefix in allowlist:
        if norm_rel == prefix or norm_rel.startswith(prefix + "/"):
            return True
    return False


def _has_importorskip_db_database(tree: ast.AST) -> bool:
    """Return True if *tree* contains ``pytest.importorskip("db.database")``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # pytest.importorskip(...) or importorskip(...)
        is_importorskip = False
        if isinstance(func, ast.Attribute) and func.attr == "importorskip":
            if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                is_importorskip = True
        if isinstance(func, ast.Name) and func.id == "importorskip":
            is_importorskip = True
        if not is_importorskip:
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            if node.args[0].value == "db.database":
                return True
    return False


def _is_pytest_fixture(deco: ast.expr) -> bool:
    """Return True if *deco* is ``pytest.fixture`` or ``@pytest.fixture(...)``."""
    if isinstance(deco, ast.Attribute) and deco.attr == "fixture":
        if isinstance(deco.value, ast.Name) and deco.value.id == "pytest":
            return True
    if isinstance(deco, ast.Name) and deco.id == "fixture":
        return True
    if isinstance(deco, ast.Call):
        return _is_pytest_fixture(deco.func)
    return False


def _py_files():
    """Yield all tracked .py files relative to repo root.

    Uses ``git ls-files`` when available so untracked files are never
    scanned.  Falls back to a filesystem walk (excluding ``.git``,
    ``node_modules``, ``docs/archive``) only if git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            yield line.replace("/", os.sep)
    except (FileNotFoundError, subprocess.CalledProcessError):
        for p in REPO.rglob("*.py"):
            rel = str(p.relative_to(REPO))
            parts = rel.split(os.sep)
            if parts[0] in (".git", "node_modules", "docs" + os.sep + "archive"):
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
        db.database is absent.  The importorskip exemption is AST-based so
        comments and unrelated string matches do not cause false negatives.
        """
        violations = []
        for rel in _py_files():
            if _in_allowlist(rel, ALLOWLIST_IMPORT_DB_DATABASE):
                continue
            try:
                text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # AST-based check: skip files that contain a real
            # pytest.importorskip("db.database") call.
            if rel.startswith("tests" + os.sep):
                try:
                    tree = ast.parse(text, filename=rel)
                except SyntaxError:
                    tree = None
                if tree is not None and _has_importorskip_db_database(tree):
                    continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "from db.database" in line or "import db.database" in line:
                    violations.append(f"{rel}:{i}: {line.strip()}")
                if re.match(r"from\s+db\s+import\s+.*\bdatabase\b", stripped):
                    violations.append(f"{rel}:{i}: {line.strip()}")
        assert not violations, "db.database imports found:\n" + "\n".join(violations)

    def test_py_files_enumerates_tracked_only(self):
        """_py_files() must not include untracked files.

        Creates a temporary git repo with one tracked and one untracked .py
        file, then verifies only the tracked file is yielded.
        """
        import tempfile

        # Build an env that strips git repo env vars so the temp repo
        # is not confused with the enclosing worktree (e.g. when run
        # from a git hook).
        clean_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("GIT_")
        }
        clean_env["GIT_AUTHOR_NAME"] = "test"
        clean_env["GIT_AUTHOR_EMAIL"] = "t@t"
        clean_env["GIT_COMMITTER_NAME"] = "test"
        clean_env["GIT_COMMITTER_EMAIL"] = "t@t"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "tracked.py").write_text("# tracked\n")
            (tmp / "untracked.py").write_text("# untracked\n")
            subprocess.run(["git", "init"], cwd=str(tmp), capture_output=True, check=True, env=clean_env)
            subprocess.run(["git", "add", "tracked.py"], cwd=str(tmp), capture_output=True, check=True, env=clean_env)
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=str(tmp), capture_output=True, check=True,
                env=clean_env,
            )

            result = subprocess.run(
                ["git", "ls-files", "*.py"],
                cwd=str(tmp),
                capture_output=True,
                text=True,
                check=True,
                env=clean_env,
            )
            files = result.stdout.splitlines()
            assert "tracked.py" in files, "tracked.py must be listed"
            assert "untracked.py" not in files, "untracked.py must NOT be listed"

    def test_no_retired_fixture_definitions(self):
        """(f) No pytest fixture named tmp_db or db_conn under conftest.py/tests/.

        Uses AST parsing — comments and docs do not trigger false positives.
        """
        RETIRED_NAMES = {"tmp_db", "db_conn"}
        violations = []

        for rel in _py_files():
            # Only scan conftest.py (any level) and files under tests/
            basename = os.path.basename(rel)
            is_conftest = basename == "conftest.py"
            is_tests = rel.startswith("tests" + os.sep)
            if not (is_conftest or is_tests):
                continue
            try:
                text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name not in RETIRED_NAMES:
                    continue
                for deco in node.decorator_list:
                    if _is_pytest_fixture(deco):
                        violations.append(f"{rel}:{node.lineno}: @pytest.fixture def {node.name}")
                        break
        assert not violations, (
            "Retired fixture definitions found (must not exist):\n"
            + "\n".join(violations)
        )

    def test_no_pytz_import_without_declaration(self):
        """No tracked .py imports pytz unless declared in requirements*.txt."""
        declared = set()
        for req in REPO.glob("requirements*.txt"):
            for line in req.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                if re.match(r"pytz\b", stripped, re.IGNORECASE):
                    declared.add(req.name)
        if declared:
            return  # pytz is declared; nothing to guard

        violations = []
        for rel in _py_files():
            if _in_allowlist(rel, {"docs/archive", "notebooks/archive", "tests/test_no_retired_sources.py"}):
                continue
            try:
                text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if re.match(r"(import\s+pytz|from\s+pytz\s+import)", stripped):
                    violations.append(f"{rel}:{i}: {line.strip()}")
        assert not violations, (
            "pytz imports found without declaration in requirements*.txt:\n"
            + "\n".join(violations)
        )
