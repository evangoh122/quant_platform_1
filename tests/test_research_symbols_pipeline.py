"""tests/test_research_symbols_pipeline.py — research symbols stay research-only.

Static wiring tests for owner decision 2026-10-22 (option D of
``.agents/requests/SOL-commodity-etfs-advice.txt``):

* adjusted silver (``silver/08``) unions ``research_universe`` into its symbol set;
* the corporate-action screen includes the research symbols, so ETF reverse
  splits (USO/UNG) are fetched;
* ``gold_tradable_universe`` is built before adjusted silver (it is adjusted
  silver's symbol source);
* research symbols never reach ``gold_ohlcv_features`` /
  ``gold_model_features`` / ``scripts/publish_baseline_signals.py``.

No Spark, no warehouse: the tests read the production SQL/Python text and its
AST, so a change to the production files is what makes them pass or fail.
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNNER = _REPO_ROOT / "pipelines" / "run_silver_gold.py"
_SILVER08 = _REPO_ROOT / "silver" / "08_silver_ohlcv_day_adjusted.sql"
_CA_NOTEBOOK = _REPO_ROOT / "notebooks" / "refresh_bronze_corporate_actions.py"
_GOLD_OHLCV = _REPO_ROOT / "gold" / "01_gold_ohlcv_features.sql"
_GOLD_MATRIX = _REPO_ROOT / "gold" / "05_gold_model_features.sql"
_PUBLISH = _REPO_ROOT / "scripts" / "publish_baseline_signals.py"

_RESEARCH_SYMBOLS = ("GLD", "IAU", "SLV", "SIVR", "USO",
                     "BNO", "UNG", "CPER", "PPLT", "PALL")

# Production files allowed to know about the research group at all. Everything
# else in silver/, gold/, pipelines/, scripts/, notebooks/, ml/, api/, agent/
# must stay research-free, which is what keeps research symbols out of model
# features and published signals.
_RESEARCH_ALLOWED_FILES = {
    "config/research_symbols.py",
    "config/research_symbols.yaml",
    "pipelines/run_silver_gold.py",
    "silver/08_silver_ohlcv_day_adjusted.sql",
    "notebooks/refresh_bronze_corporate_actions.py",
}
_SCAN_ROOTS = ("silver", "gold", "pipelines", "scripts", "notebooks",
               "ml", "api", "agent")
_SCAN_SUFFIXES = {".py", ".sql", ".yaml", ".yml"}
_RESEARCH_MARKERS = ("research_universe", "load_research_symbols",
                     "research_symbols")


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _strip_sql_comments(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )


def _extract_view(sql_text: str, view_name: str) -> str:
    """Return the real ``CREATE OR REPLACE TEMP VIEW <name> AS ...;`` statement."""
    pattern = (
        rf"CREATE\s+OR\s+REPLACE\s+TEMP\s+VIEW\s+{re.escape(view_name)}"
        rf"\s+AS\s+.*?;"
    )
    match = re.search(pattern, _strip_sql_comments(sql_text), re.DOTALL | re.IGNORECASE)
    assert match, f"view {view_name!r} not found"
    return match.group(0)


def _research_union_problems(view_sql: str) -> list[str]:
    """Invariants of adjusted silver's symbol-set view (empty == healthy)."""
    body = view_sql.lower()
    problems = []
    if "research_universe" not in body:
        problems.append("adjusted silver does not union the research_universe view")
    if "gold_tradable_universe" not in body:
        problems.append("adjusted silver lost the ever-in-Gold symbol source")
    for benchmark in ("spy", "rsp", "qqq"):
        if f"'{benchmark}'" not in body:
            problems.append(f"adjusted silver lost benchmark {benchmark.upper()}")
    return problems


class TestAdjustedSilverResearchUnion:
    def test_view_unions_research_symbols(self):
        statement = _extract_view(
            _SILVER08.read_text(encoding="utf-8"), "_universe"
        )
        assert "research_universe" in _strip_sql_comments(statement).lower()

    def test_view_keeps_gold_universe_and_benchmarks(self):
        statement = _extract_view(
            _SILVER08.read_text(encoding="utf-8"), "_universe"
        )
        assert _research_union_problems(statement) == []

    def test_view_does_not_hardcode_the_research_symbols(self):
        """The group is configuration-driven; the SQL must not list the ETFs."""
        statement = _extract_view(
            _SILVER08.read_text(encoding="utf-8"), "_universe"
        )
        hardcoded = [s for s in _RESEARCH_SYMBOLS if f"'{s}'" in statement.upper()]
        assert not hardcoded, (
            f"silver/08 hardcodes research symbols {hardcoded}; read "
            f"config/research_symbols.yaml instead"
        )

    def test_mutation_dropping_the_union_is_detected(self):
        """Mutation proof: without the research union the invariant fails."""
        statement = _extract_view(
            _SILVER08.read_text(encoding="utf-8"), "_universe"
        )
        mutated = "\n".join(
            line for line in statement.splitlines()
            if "research_universe" not in line.lower()
        )
        assert "research_universe" not in mutated.lower(), "mutation must remove the union"
        problems = _research_union_problems(mutated)
        assert any("research_universe" in p for p in problems), (
            f"guard did not detect the dropped union: {problems}"
        )


# ---------------------------------------------------------------------------
# Corporate actions: pure SQL builder
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ca_notebook():
    spec = importlib.util.spec_from_file_location(
        "research_symbols_ca_notebook", _CA_NOTEBOOK
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCorporateActionUniverse:
    def test_builder_includes_gold_universe_benchmarks_and_research(self, ca_notebook):
        sql = ca_notebook.build_universe_sql("cat.sch", ["GLD", "UNG"])
        assert "cat.sch.gold_tradable_universe" in sql
        for benchmark in ("SPY", "RSP", "QQQ"):
            assert f"'{benchmark}'" in sql
        assert "UNION SELECT 'GLD'" in sql
        assert "UNION SELECT 'UNG'" in sql

    def test_builder_without_research_symbols_stays_trading_only(self, ca_notebook):
        sql = ca_notebook.build_universe_sql("cat.sch", [])
        assert "research" not in sql.lower()
        for symbol in _RESEARCH_SYMBOLS:
            assert f"'{symbol}'" not in sql

    def test_builder_rejects_a_symbol_that_could_break_the_literal(self, ca_notebook):
        with pytest.raises(ValueError, match="invalid research symbol"):
            ca_notebook.build_universe_sql("cat.sch", ["GLD' OR 1=1 --"])

    def test_builder_rejects_lowercase_symbols(self, ca_notebook):
        with pytest.raises(ValueError, match="upper-case"):
            ca_notebook.build_universe_sql("cat.sch", ["gld"])

    def test_main_feeds_the_configured_group_into_the_builder(self):
        source = _CA_NOTEBOOK.read_text(encoding="utf-8")
        assert _ca_wiring_problems(source) == []

    def test_mutation_dropping_the_group_from_main_is_detected(self):
        """Mutation proof: main() building the SQL without the loader fails."""
        source = _CA_NOTEBOOK.read_text(encoding="utf-8")
        mutated = source.replace(
            "build_universe_sql(FQN, load_research_symbols())",
            "build_universe_sql(FQN)",
        )
        assert mutated != source, "mutation must change the wiring"
        assert _ca_wiring_problems(mutated), (
            "guard did not detect the dropped research symbols in main()"
        )


def _ca_wiring_problems(source: str) -> list[str]:
    problems = []
    if "from config.research_symbols import" not in source:
        problems.append("notebook does not import the research-symbol loader")
    if not re.search(
        r"build_universe_sql\(\s*FQN\s*,\s*load_research_symbols\(\)\s*\)",
        source,
    ):
        problems.append(
            "corporate-action universe is not built from load_research_symbols()"
        )
    return problems


# ---------------------------------------------------------------------------
# Pipeline step order
# ---------------------------------------------------------------------------

def _module_literal(path: Path, name: str):
    """Literal value of a module-level ``NAME = ...`` assignment (e.g. STEPS)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} assignment not found in {path}")


def _read_steps() -> list[tuple[str, str, str]]:
    return [tuple(step) for step in _module_literal(_RUNNER, "STEPS")]


def _order_problems(steps) -> list[str]:
    names = [step[0] for step in steps]
    problems = []

    def position(name: str) -> int:
        return names.index(name) if name in names else -1

    universe = position("gold_tradable_universe")
    adjusted = position("silver_ohlcv_day_adjusted")
    breaks = position("data_quality_breaks")

    if universe < 0:
        problems.append("gold_tradable_universe step is missing")
    if adjusted < 0:
        problems.append("silver_ohlcv_day_adjusted step is missing")
    if universe >= 0 and adjusted >= 0 and universe > adjusted:
        problems.append(
            "gold_tradable_universe is built after silver_ohlcv_day_adjusted, "
            "but adjusted silver reads it as its symbol filter"
        )
    if adjusted >= 0 and breaks >= 0 and adjusted > breaks:
        problems.append(
            "silver_ohlcv_day_adjusted is built after data_quality_breaks"
        )
    return problems


class TestPipelineOrder:
    def test_gold_universe_is_built_before_adjusted_silver(self):
        assert _order_problems(_read_steps()) == []

    def test_no_step_was_dropped_by_the_reorder(self):
        steps = _read_steps()
        targets = set(_module_literal(_RUNNER, "TARGET_TABLES"))
        assert {name for name, _path, _kind in steps} == targets

    def test_every_step_path_exists(self):
        for name, rel, _kind in _read_steps():
            assert (_REPO_ROOT / rel).is_file(), f"step {name} path {rel} is missing"

    def test_mutation_restoring_the_old_order_is_detected(self):
        """Mutation proof: the previous order (universe built last) fails."""
        steps = _read_steps()
        universe_step = next(s for s in steps if s[0] == "gold_tradable_universe")
        mutated = [s for s in steps if s[0] != "gold_tradable_universe"]
        mutated.append(universe_step)  # old position: after gold_model_features
        problems = _order_problems(mutated)
        assert any("after silver_ohlcv_day_adjusted" in p for p in problems), (
            f"guard did not detect the restored old order: {problems}"
        )


# ---------------------------------------------------------------------------
# research_universe temp view carries data_source (owner rule: every new view)
# ---------------------------------------------------------------------------

_RESEARCH_DATA_SOURCE = "massive"
_RESEARCH_VIEW_SCHEMA_COLUMNS = (
    "SYMBOL STRING NOT NULL",
    "DATA_SOURCE STRING NOT NULL",
)


@pytest.fixture(scope="module")
def runner_module():
    """The production runner, importable without pyspark (CI blocks it)."""
    import pipelines.run_silver_gold

    return pipelines.run_silver_gold


class _RecordingDataFrame:
    """DataFrame stand-in that records the temp view it registered."""

    def __init__(self, spark: "_RecordingSpark") -> None:
        self._spark = spark

    def createOrReplaceTempView(self, name: str) -> None:
        self._spark.view_name = name


class _RecordingSpark:
    """Fake SparkSession that records ``createDataFrame`` arguments."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.view_name = None

    def createDataFrame(self, rows, schema=None):
        self.calls.append({"rows": list(rows), "schema": schema})
        return _RecordingDataFrame(self)


def _research_view_problems(rows, schema) -> list[str]:
    """Invariants of the research_universe registration (empty == healthy)."""
    problems = []
    if not rows:
        problems.append("research_universe has no rows")
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 2:
            problems.append(f"row {row!r} is not (symbol, data_source)")
            continue
        symbol, data_source = row
        if not isinstance(symbol, str) or not symbol:
            problems.append(f"row {row!r} has no symbol")
        if not isinstance(data_source, str) or not data_source:
            problems.append(f"row {row!r} has no data_source")
    if not isinstance(schema, str):
        problems.append(f"schema is not a DDL string: {schema!r}")
        return problems
    normalized = " ".join(schema.upper().split())
    for column in _RESEARCH_VIEW_SCHEMA_COLUMNS:
        if column not in normalized:
            problems.append(f"schema lacks the NOT NULL column {column!r}")
    return problems


class TestResearchUniverseView:
    def _register(self, runner_module):
        spark = _RecordingSpark()
        returned = runner_module.register_research_universe(spark)
        assert len(spark.calls) == 1, (
            f"expected exactly one createDataFrame call, got {len(spark.calls)}"
        )
        return returned, spark, spark.calls[0]["rows"], spark.calls[0]["schema"]

    def test_rows_carry_the_validated_data_source(self, runner_module):
        returned, _spark, rows, schema = self._register(runner_module)
        assert returned == list(_RESEARCH_SYMBOLS)
        assert rows == [
            (symbol, _RESEARCH_DATA_SOURCE) for symbol in _RESEARCH_SYMBOLS
        ], f"research_universe rows lost data_source: {rows}"
        assert _research_view_problems(rows, schema) == []

    def test_schema_is_ddl_with_both_not_null_columns(self, runner_module):
        _returned, _spark, rows, schema = self._register(runner_module)
        assert isinstance(schema, str), (
            f"createDataFrame must receive the DDL string, got {schema!r}"
        )
        normalized = " ".join(schema.upper().split())
        for column in _RESEARCH_VIEW_SCHEMA_COLUMNS:
            assert column in normalized, f"schema lacks {column!r}: {schema!r}"
        assert _research_view_problems(rows, schema) == []

    def test_view_is_registered_under_research_universe(self, runner_module):
        _returned, spark, _rows, _schema = self._register(runner_module)
        assert spark.view_name == "research_universe"

    def test_rows_match_the_loader_registry(self, runner_module):
        """Rows come from the validated loader, not an ad-hoc YAML re-read."""
        from config.research_symbols import load_research_registry

        registry = load_research_registry()
        _returned, _spark, rows, _schema = self._register(runner_module)
        assert rows == [
            (symbol, meta["data_source"]) for symbol, meta in registry.items()
        ]

    def test_mutation_dropping_data_source_from_the_rows_is_detected(
        self, runner_module
    ):
        """Mutation proof: a symbol-only view fails the invariant."""
        _returned, _spark, rows, schema = self._register(runner_module)
        mutated = [(symbol,) for symbol, _data_source in rows]
        assert mutated != rows, "mutation must drop data_source"
        problems = _research_view_problems(mutated, schema)
        assert any("(symbol, data_source)" in p for p in problems), (
            f"guard did not detect the dropped data_source: {problems}"
        )

    def test_mutation_stripping_not_null_from_the_schema_is_detected(
        self, runner_module
    ):
        """Mutation proof: a nullable schema fails the invariant."""
        _returned, _spark, rows, schema = self._register(runner_module)
        mutated = schema.replace(" NOT NULL", "")
        assert mutated != schema, "mutation must strip NOT NULL"
        problems = _research_view_problems(rows, mutated)
        assert any("NOT NULL" in p for p in problems), (
            f"guard did not detect the lost NOT NULL: {problems}"
        )


# ---------------------------------------------------------------------------
# Signals guard: research symbols never reach the model matrix publication
# ---------------------------------------------------------------------------

def _scan_production_sources() -> dict[str, str]:
    files: dict[str, str] = {}
    for root in _SCAN_ROOTS:
        base = _REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in _SCAN_SUFFIXES or not path.is_file():
                continue
            files[path.relative_to(_REPO_ROOT).as_posix()] = path.read_text(
                encoding="utf-8", errors="ignore"
            )
    return files


def _mentions_research(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _RESEARCH_MARKERS)


def _guard_offenders(files: dict[str, str]) -> list[str]:
    return sorted(
        rel for rel, text in files.items()
        if rel not in _RESEARCH_ALLOWED_FILES and _mentions_research(text)
    )


def _model_matrix_problems(
    ohlcv_sql: str, matrix_sql: str, publish_source: str
) -> list[str]:
    """Research symbols must not reach the minute spine / model matrix / signals."""
    ohlcv = _strip_sql_comments(ohlcv_sql).lower()
    matrix = _strip_sql_comments(matrix_sql).lower()
    publish = publish_source.lower()

    problems = []
    if "symbol in (select symbol from universe)" not in ohlcv:
        problems.append(
            "gold/01 minute spine is not filtered by the trading universe view"
        )
    if "research" in ohlcv:
        problems.append("gold/01 (minute spine) references research symbols")
    if "gold_ohlcv_features" not in matrix:
        problems.append("gold/05 spine is not gold_ohlcv_features")
    if "research" in matrix:
        problems.append("gold/05 (model matrix) references research symbols")
    if "gold_model_features" not in publish:
        problems.append("publish script does not read gold_model_features")
    if "research" in publish:
        problems.append("publish script references research symbols")
    return problems


class TestSignalsGuard:
    def test_only_the_allowlisted_files_mention_research(self):
        files = _scan_production_sources()
        assert "gold/01_gold_ohlcv_features.sql" in files
        assert "gold/05_gold_model_features.sql" in files
        assert "scripts/publish_baseline_signals.py" in files
        assert _guard_offenders(files) == []

    def test_model_matrix_inputs_are_filtered_by_the_trading_universe_only(self):
        problems = _model_matrix_problems(
            _GOLD_OHLCV.read_text(encoding="utf-8"),
            _GOLD_MATRIX.read_text(encoding="utf-8"),
            _PUBLISH.read_text(encoding="utf-8"),
        )
        assert problems == []

    def test_trading_universe_view_does_not_load_research_symbols(self):
        source = _RUNNER.read_text(encoding="utf-8")
        assert _trading_view_problems(source) == []

    def test_mutation_adding_research_to_the_model_feature_filter_is_detected(self):
        """Mutation proof: a research filter on gold/01 must fail the guard."""
        files = _scan_production_sources()
        path = "gold/01_gold_ohlcv_features.sql"
        files[path] = files[path] + (
            "\n      AND symbol IN (SELECT symbol FROM research_universe)\n"
        )
        assert path in _guard_offenders(files)

    def test_mutation_adding_research_to_the_publish_script_is_detected(self):
        files = _scan_production_sources()
        path = "scripts/publish_baseline_signals.py"
        files[path] = files[path] + "\nfrom config.research_symbols import load_research_symbols\n"
        assert path in _guard_offenders(files)

    def test_mutation_merging_the_groups_into_the_trading_view_is_detected(self):
        source = _RUNNER.read_text(encoding="utf-8")
        mutated = source.replace(
            'df.createOrReplaceTempView("universe")',
            'df.createOrReplaceTempView("universe")\n    load_research_symbols()',
            1,
        )
        assert mutated != source, "mutation must change the trading universe view"
        assert _trading_view_problems(mutated), (
            "guard did not detect research symbols merged into the trading view"
        )


def _trading_view_problems(runner_source: str) -> list[str]:
    """``register_universe`` must register the trading group only."""
    tree = ast.parse(runner_source)
    function_source = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "register_universe":
            function_source = ast.get_source_segment(runner_source, node)
            break
    assert function_source, "register_universe not found"

    problems = []
    if "research" in function_source.lower():
        problems.append("register_universe references the research group")
    if 'createOrReplaceTempView("universe")' not in function_source:
        problems.append('register_universe does not register the "universe" view')
    return problems
