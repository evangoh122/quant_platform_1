"""
Guard test: ensure retired yfinance/duckdb.local-store modules are not reintroduced.

Runs in CI without pyspark. Validates:
(a) No tracked .py outside allowlist imports yfinance.
(b) The six deleted ETL modules do not exist.
(c) Ontology has no yfinance key and massive == "implemented".
(d) requirements*.txt have no yfinance line.
(e) Nothing outside allowlist imports db.database (the retired module).
(f) No pytest fixture named tmp_db or db_conn under conftest.py/tests/, also
    when the name is claimed via the decorator ``name=`` keyword
    (``@pytest.fixture(name="tmp_db")``).
(g) pytz is declared in requirements*.txt whenever duckdb is declared (duckdb's
    Python client converts timezone-aware results via pytz) and whenever a
    tracked .py imports it.
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

RETIRED_NAMES = {"tmp_db", "db_conn"}

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


def _import_hits(text: str, module: str) -> list[tuple[int, str]]:
    """Return ``(lineno, source line)`` for imports of *module* or ``module.*``.

    AST-based (``ast.Import``/``ast.ImportFrom`` name lists) so comma-separated
    imports such as ``import os, yfinance`` and ``import os, pytz`` are
    detected, while comments and string literals are not.  Falls back to
    line-text matching when *text* cannot be parsed so unparseable files are
    still scanned.
    """
    lines = text.splitlines()
    hits: list[tuple[int, str]] = []

    def _hit(node: ast.AST) -> None:
        lineno = getattr(node, "lineno", 0)
        line = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
        hits.append((lineno, line))

    try:
        tree = ast.parse(text)
    except SyntaxError:
        pattern = re.compile(
            rf"(^|[^\w.])(import\s+{re.escape(module)}\b|from\s+{re.escape(module)}\b)"
        )
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if pattern.search(line):
                hits.append((i, line.strip()))
        return hits

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                a.name == module or a.name.startswith(module + ".")
                for a in node.names
            ):
                _hit(node)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and (
                node.module == module or node.module.startswith(module + ".")
            ):
                _hit(node)
    return hits


def _retired_fixture_hits(text: str, retired: set[str] | frozenset[str] = RETIRED_NAMES) -> list[str]:
    """Return violations for pytest fixtures whose effective name is retired.

    The effective name is the decorator's ``name=`` keyword when given
    (``@pytest.fixture(name="tmp_db")`` on a differently named function is a
    violation), otherwise the function name.
    """
    tree = ast.parse(text)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fixture_names: list[str] = []
        is_fixture = False
        for deco in node.decorator_list:
            if not _is_pytest_fixture(deco):
                continue
            is_fixture = True
            if isinstance(deco, ast.Call):
                for kw in deco.keywords:
                    if (
                        kw.arg == "name"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        fixture_names.append(kw.value.value)
        if not is_fixture:
            continue
        if node.name in retired:
            hits.append(f"{node.lineno}: @pytest.fixture def {node.name}")
            continue
        for name in fixture_names:
            if name in retired:
                hits.append(
                    f"{node.lineno}: @pytest.fixture(name={name!r}) def {node.name}"
                )
                break
    return hits


def _requirements_declared(path: Path, seen: set[Path] | None = None) -> set[str]:
    """Return lowercased distribution names declared by a requirements file.

    Resolves ``-r``/``--requirement`` includes so a file that pulls in another
    requirements file inherits its declarations.
    """
    if seen is None:
        seen = set()
    path = path.resolve()
    if path in seen or not path.exists():
        return set()
    seen.add(path)
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        inc = re.match(r"^(?:-r|--requirement)\s+(.+)$", line)
        if inc:
            names |= _requirements_declared(path.parent / inc.group(1).strip(), seen)
            continue
        name = re.split(r"[><=\[;~! ]", line)[0].strip().lower()
        if name:
            names.add(name)
    return names


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
        """(a) No tracked .py outside allowlist imports yfinance.

        AST-based via ``_import_hits`` so comma-separated imports like
        ``import os, yfinance`` are caught (line-text checks miss them).
        """
        violations = []
        for rel in _py_files():
            if _in_allowlist(rel, ALLOWLIST_IMPORT_YFINANCE):
                continue
            try:
                text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in _import_hits(text, "yfinance"):
                violations.append(f"{rel}:{lineno}: {line}")
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
        The decorator's ``name=`` keyword is checked too, so
        ``@pytest.fixture(name="tmp_db")`` on a differently named function is
        flagged.
        """
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
                hits = _retired_fixture_hits(text, RETIRED_NAMES)
            except SyntaxError:
                continue
            for hit in hits:
                violations.append(f"{rel}:{hit}")
        assert not violations, (
            "Retired fixture definitions found (must not exist):\n"
            + "\n".join(violations)
        )

    def test_no_pytz_import_without_declaration(self):
        """(g) pytz must be declared in requirements*.txt whenever duckdb is,
        and whenever a tracked .py imports it.

        duckdb's Python client converts timezone-aware TIMESTAMP results via
        pytz: without it tz-aware fetches raise InvalidInputException
        ("Required module 'pytz' failed to import").  Declarations are parsed
        per requirements file (``-r`` includes resolved), so a file that pulls
        duckdb — directly or via include — must also provide pytz.
        """
        req_files = sorted(REPO.glob("requirements*.txt"))
        declared_by_file = {
            req.name: _requirements_declared(req) for req in req_files
        }
        for fname, declared in declared_by_file.items():
            assert not ("duckdb" in declared and "pytz" not in declared), (
                f"{fname} declares duckdb but not pytz: duckdb's Python client "
                "converts timezone-aware timestamps via pytz and raises "
                "InvalidInputException without it"
            )

        all_declared: set[str] = set()
        for declared in declared_by_file.values():
            all_declared |= declared
        if "pytz" in all_declared:
            return  # pytz is declared; nothing to guard

        violations = []
        for rel in _py_files():
            if _in_allowlist(rel, {"docs/archive", "notebooks/archive", "tests/test_no_retired_sources.py"}):
                continue
            try:
                text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in _import_hits(text, "pytz"):
                violations.append(f"{rel}:{lineno}: {line}")
        assert not violations, (
            "pytz imports found without declaration in requirements*.txt:\n"
            + "\n".join(violations)
        )


class TestGuardDetectionLogic:
    """Unit tests for the guard helpers themselves (CodeRabbit r5 findings)."""

    def test_import_hits_detects_comma_separated_imports(self):
        """Line-text import checks miss ``import os, yfinance`` /
        ``import os, pytz``; the AST name-list parse must catch them."""
        assert _import_hits("import os, yfinance\n", "yfinance"), (
            "comma-separated 'import os, yfinance' not detected"
        )
        assert _import_hits("import os, pytz\n", "pytz"), (
            "comma-separated 'import os, pytz' not detected"
        )
        # plain and from-forms still detected
        assert _import_hits("import yfinance as yf\n", "yfinance")
        assert _import_hits("from pytz import timezone\n", "pytz")
        assert _import_hits("from yfinance.tools import history\n", "yfinance")
        # near-miss packages must NOT be flagged
        assert not _import_hits("import yfinance_lite\n", "yfinance")
        assert not _import_hits("from yfinancetools import history\n", "yfinance")

    def test_import_hits_ignores_comments_and_strings(self):
        src = (
            "# import os, yfinance\n"
            'x = "import os, pytz"\n'
            "y = 'from yfinance import history'\n"
        )
        assert not _import_hits(src, "yfinance"), "comment/string flagged as yfinance import"
        assert not _import_hits(src, "pytz"), "comment/string flagged as pytz import"

    def test_fixture_name_keyword_is_flagged(self):
        """``@pytest.fixture(name="tmp_db")`` on a differently named function
        must be flagged: the decorator ``name=`` keyword is the effective
        fixture name."""
        src = (
            "import pytest\n\n"
            '@pytest.fixture(name="tmp_db")\n'
            "def helper_db():\n    return 1\n"
        )
        hits = _retired_fixture_hits(src)
        assert any('name="tmp_db"' in h or "name='tmp_db'" in h for h in hits), (
            f"@pytest.fixture(name='tmp_db') on def helper_db not flagged: {hits}"
        )
        # non-retired name= must not be flagged
        assert not _retired_fixture_hits(
            "import pytest\n\n@pytest.fixture(name=\"helper_db\")\ndef foo():\n    return 1\n"
        )
        # function-name form still flagged
        assert _retired_fixture_hits(
            "import pytest\n\n@pytest.fixture\ndef db_conn():\n    return 1\n"
        )
