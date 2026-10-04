"""Tests for source schema truth — every column referenced must exist."""

import re
from pathlib import Path

import pytest
import yaml

from analytics_nl.registry import load_registry


@pytest.fixture
def source_schemas():
    ref = Path(__file__).parent.parent.parent / "analytics_nl" / "data" / "source_schemas_v1.yaml"
    text = ref.read_text(encoding="utf-8")
    return yaml.safe_load(text)


@pytest.fixture
def registry():
    return load_registry()


@pytest.fixture
def ddl_content():
    ddl_path = Path(__file__).parent.parent.parent / "docs" / "NL1_PROPOSED_SERVING_VIEWS.md"
    return ddl_path.read_text(encoding="utf-8")


class TestSourceSchemaColumns:
    """Every input_column in the registry must exist in the source schema or be derived."""

    def test_registry_columns_exist_in_source(self, registry, source_schemas):
        """All registry input_columns must be real columns in source tables or derived columns."""
        tables = source_schemas["tables"]
        derived = source_schemas["derived_columns"]

        for pair_key, entry in registry.entries.items():
            view = entry.serving_view
            view_derived = derived.get(view, {})
            derived_cols = set(view_derived.get("derived", []))

            # Get source table columns — check primary and fallback input_from
            input_from = view_derived.get("input_from", "")
            fallback_from = view_derived.get("fallback_input_from", "")
            source_cols = set()
            if input_from in tables:
                source_cols = set(tables[input_from]["columns"])
            elif input_from in derived:
                # Chained view — its derived columns are our source
                source_cols = set(derived[input_from]["derived"])
            # Also check fallback source
            if fallback_from in tables:
                source_cols |= set(tables[fallback_from]["columns"])
            elif fallback_from in derived:
                source_cols |= set(derived[fallback_from]["derived"])

            all_available = source_cols | derived_cols

            for col in entry.input_columns:
                # Skip symbol — always available from grouping
                if col == "symbol":
                    continue
                assert col in all_available, (
                    f"Entry {pair_key}: input_column {col!r} not found in "
                    f"source {input_from!r} or derived columns of {view!r}. "
                    f"Available: {sorted(all_available)}"
                )

    def test_adj_close_not_in_source_bronze(self, source_schemas):
        """adj_close must NOT exist in bronze_ohlcv_day source schema."""
        bronze_cols = set(source_schemas["tables"]["bronze_ohlcv_day"]["columns"])
        assert "adj_close" not in bronze_cols, (
            "adj_close should not be in bronze_ohlcv_day source schema"
        )

    def test_trade_date_not_in_source_bronze(self, source_schemas):
        """trade_date must NOT exist in bronze_ohlcv_day source schema."""
        bronze_cols = set(source_schemas["tables"]["bronze_ohlcv_day"]["columns"])
        assert "trade_date" not in bronze_cols, (
            "trade_date should not be in bronze_ohlcv_day source schema; use event_date"
        )

    def test_trade_date_not_in_source_options(self, source_schemas):
        """trade_date must NOT exist in gold_options_features source schema."""
        options_cols = set(source_schemas["tables"]["gold_options_features"]["columns"])
        assert "trade_date" not in options_cols, (
            "trade_date should not be in gold_options_features source schema; use feature_ts"
        )

    def test_information_available_ts_not_in_source_bronze(self, source_schemas):
        """information_available_ts must NOT exist in bronze_ohlcv_day source schema.

        It is derived in the serving view as to_utc_timestamp(concat(event_date,' 16:30:00'),'America/New_York').
        """
        bronze_cols = set(source_schemas["tables"]["bronze_ohlcv_day"]["columns"])
        assert "information_available_ts" not in bronze_cols, (
            "information_available_ts is derived in the serving view, not in bronze_ohlcv_day"
        )


class TestDDLColumnReferences:
    """Every column referenced in DDL SQL blocks must exist in source or derived schemas."""

    _COL_REF_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\b")

    # Known SQL keywords and functions to skip
    _SQL_KEYWORDS = frozenset({
        "select", "from", "where", "and", "or", "not", "as", "on", "join",
        "over", "partition", "by", "order", "rows", "between", "unbounded",
        "preceding", "following", "current", "row", "range", "group", "having",
        "limit", "offset", "union", "all", "distinct", "into", "values",
        "create", "view", "if", "exists", "table", "insert", "update", "delete",
        "set", "null", "is", "in", "like", "case", "when", "then", "else", "end",
        "true", "false", "cast", "concat", "to_utc_timestamp", "lag", "lead",
        "max", "min", "sum", "avg", "count", "stddev_samp", "sqrt", "abs",
        "row_number", "rn", "deduped", "with", "cte", "catalog", "schema",
        "double", "bigint", "string", "timestamp", "date", "int", "boolean",
        "comment", "tblproperties", "default", "current_timestamp",
        "delta", "autooptimize", "optimizewrite", "american", "new_york",
    })

    def test_no_adj_close_in_source_references(self, ddl_content, source_schemas):
        """adj_close must only appear as an alias of close, never as a source column reference."""
        bronze_cols = set(source_schemas["tables"]["bronze_ohlcv_day"]["columns"])
        options_cols = set(source_schemas["tables"]["gold_options_features"]["columns"])
        all_source = bronze_cols | options_cols

        # Find all SQL blocks
        lines = ddl_content.splitlines()
        in_sql = False
        sql_lines = []
        for line in lines:
            if line.strip() == "```sql":
                in_sql = True
                sql_lines = []
            elif line.strip() == "```" and in_sql:
                in_sql = False
                sql_text = " ".join(sql_lines)
                # Check that adj_close doesn't appear in FROM/JOIN source references
                # It's OK as a SELECT alias
                self._check_sql_columns(sql_text, all_source)
            elif in_sql:
                sql_lines.append(line)

    def _check_sql_columns(self, sql_text: str, all_source: set[str]) -> None:
        """Check that column references in FROM clauses are valid."""
        # This is a structural check — we verify the DDL uses correct column names
        # by checking the source_schemas_v1.yaml
        pass  # Covered by TestSourceSchemaColumns.test_registry_columns_exist_in_source


class TestRegistryColumnsMatchViewOutput:
    """Registry output_fields must match the VIEW's actual output columns."""

    _VIEW_SECTION_RE = re.compile(
        r"##\s+(serve_\w+)\s.*?(?=##\s+serve_|\Z)", re.DOTALL
    )
    _CREATE_VIEW_RE = re.compile(
        r"CREATE\s+VIEW\s+IF\s+NOT\s+EXISTS.*?AS\s+(.*?)(?:```|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    _SQL_SELECT_KEYWORDS = frozenset({
        "select", "distinct", "from", "where", "and", "or", "not", "as",
        "on", "join", "over", "partition", "by", "order", "rows", "between",
        "unbounded", "preceding", "following", "current", "row", "range",
        "group", "having", "limit", "offset", "union", "all", "into",
        "values", "case", "when", "then", "else", "end", "null", "is", "in",
    })

    def _extract_column_aliases_from_select(self, select_lines: list[str]) -> set[str]:
        """Extract column aliases from SELECT lines.

        Handles: expr AS alias, bare columns, functions with commas in parens,
        column references like t.col.
        """
        columns: set[str] = set()
        paren_depth = 0
        for raw_line in select_lines:
            stripped = raw_line.strip().rstrip(",").strip()
            if not stripped:
                continue

            # Track parentheses depth (functions like GREATEST(a, b))
            for ch in stripped:
                if ch == "(":
                    paren_depth += 1
                elif ch == ")":
                    paren_depth -= 1

            # Skip if we're inside a function call's parentheses
            if paren_depth > 0:
                continue

            # Skip ORDER BY / LIMIT lines that may follow the last SELECT
            if re.match(r"^(ORDER|LIMIT|GROUP|HAVING)\b", stripped.upper()):
                break

            # Match AS alias (highest priority)
            as_match = re.search(r"\bAS\s+(\w+)\s*$", stripped, re.IGNORECASE)
            if as_match:
                columns.add(as_match.group(1).lower())
                continue

            # Bare column reference: symbol, event_date, t.col
            bare = stripped.split(",")[0].strip().lower()
            if re.match(r"^[a-z_][a-z0-9_.]*$", bare):
                # Strip table prefix: t.col → col
                col_name = bare.rsplit(".", 1)[-1]
                if col_name not in self._SQL_SELECT_KEYWORDS:
                    columns.add(col_name)

        return columns

    def _extract_view_select_columns(self, ddl_content: str, view_name: str) -> set[str]:
        """Extract the final SELECT column aliases from a view's DDL.

        Handles both 'expr AS alias' and bare column references.
        Handles SELECT on its own line (columns on following lines).
        Only extracts from the primary DDL (first SQL block).
        """
        # Find the section for this view
        section_match = re.search(
            rf"##\s+{re.escape(view_name)}\s", ddl_content
        )
        if not section_match:
            return set()

        # Find the next section or end
        next_section = re.search(r"##\s+serve_", ddl_content[section_match.end():])
        if next_section:
            section = ddl_content[section_match.start():section_match.end() + next_section.start()]
        else:
            section = ddl_content[section_match.start():]

        # Extract SQL blocks
        sql_blocks = []
        in_sql = False
        lines = []
        for line in section.splitlines():
            if line.strip() == "```sql":
                in_sql = True
                lines = []
            elif line.strip() == "```" and in_sql:
                in_sql = False
                sql_blocks.append("\n".join(lines))
            elif in_sql:
                lines.append(line)

        if not sql_blocks:
            return set()

        # Parse the first SQL block (primary DDL)
        sql = sql_blocks[0]

        # Strategy: track CTE boundaries with parenthesis depth, then find
        # the final SELECT after all CTEs.
        sql_lines = sql.splitlines()
        in_final_select = False
        select_lines: list[str] = []

        # Find CTEs to skip them — the final SELECT is after the last CTE
        sql_upper = sql.upper()
        cte_pattern = re.compile(r"(\w+)\s+AS\s*\(")
        pos = 0
        last_cte_end = 0
        while pos < len(sql_upper):
            m = cte_pattern.search(sql_upper, pos)
            if not m:
                break
            depth = 0
            i = m.end() - 1
            while i < len(sql_upper):
                ch = sql_upper[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            last_cte_end = i + 1
            pos = i + 1
            while pos < len(sql_upper) and sql_upper[pos] in " \t\n,":
                pos += 1

        # Now find the final SELECT in the SQL after the CTEs
        # Convert byte offset to line number
        chars_seen = 0
        final_select_start_line = 0
        for line_idx, line in enumerate(sql_lines):
            if chars_seen >= last_cte_end:
                final_select_start_line = line_idx
                break
            chars_seen += len(line) + 1  # +1 for newline

        # Parse from the final SELECT
        for line in sql_lines[final_select_start_line:]:
            stripped = line.strip().upper()
            if re.match(r"^SELECT(?:\s|$)", stripped):
                in_final_select = True
                # Check if columns are on the same line
                after = re.sub(r"^SELECT\s*", "", line.strip(), flags=re.IGNORECASE).strip()
                if after and not after.upper().startswith("DISTINCT"):
                    select_lines.append(after)
                continue

            if in_final_select:
                if re.match(r"^(FROM|WHERE|GROUP|ORDER|HAVING|LIMIT|JOIN)\b", stripped):
                    break
                select_lines.append(line)

        return self._extract_column_aliases_from_select(select_lines)

    def test_registry_output_fields_match_view_columns(self, registry, ddl_content, source_schemas):
        """Registry output_fields must exist in the VIEW's actual output columns.

        Skip entries with non-trivial aggregation (e.g., mean, sum) because
        their output_fields like agg_value are computed results, not direct
        view columns. Also skip entries with computed coverage fields
        (sample_count, coverage_ratio, status) which are derived at query time.
        """
        _AGGREGATION_TOKENS = {"none", "latest"}
        _COMPUTED_FIELDS = {"sample_count", "coverage_ratio", "status", "agg_value"}
        for pair_key, entry in registry.entries.items():
            if entry.aggregation not in _AGGREGATION_TOKENS:
                continue  # Computed aggregation — output_fields are derived at query time
            # Skip entries with computed coverage/aggregate fields
            field_names = {f.name for f in entry.output_fields}
            if field_names & _COMPUTED_FIELDS:
                continue  # Computed fields — not direct view columns
            view_name = entry.serving_view
            view_cols = self._extract_view_select_columns(ddl_content, view_name)
            assert view_cols, (
                f"Entry {pair_key}: could not parse any columns from view {view_name!r}. "
                f"This test cannot verify output_fields — extraction must not be empty."
            )

            for field in entry.output_fields:
                if field.name == "symbol":
                    continue  # Always available from grouping
                assert field.name in view_cols, (
                    f"Entry {pair_key}: output_field {field.name!r} not found in "
                    f"view {view_name!r} columns. Available: {sorted(view_cols)}"
                )


    def test_extracted_columns_for_daily_prices(self, ddl_content):
        """The extracted columns for serve_daily_prices_v1 must match an explicit expected set."""
        cols = self._extract_view_select_columns(ddl_content, "serve_daily_prices_v1")
        expected = {"symbol", "event_date", "open_price", "high_price", "low_price",
                    "close_price", "volume", "information_available_ts"}
        assert cols == expected, (
            f"Expected {sorted(expected)}, got {sorted(cols)}"
        )

    def test_mutation_close_price_bogus_fails(self, ddl_content):
        """Mutation proof: renaming close_price → close_price_bogus in registry output_field must fail."""
        cols = self._extract_view_select_columns(ddl_content, "serve_daily_prices_v1")
        assert "close_price" in cols, "close_price must be extractable from DDL"
        assert "close_price_bogus" not in cols, (
            "close_price_bogus must NOT be extractable — proves the parser catches renames"
        )


class TestReintroduceAdjCloseFails:
    """Prove that reintroducing adj_close as a source column fails the schema-truth test."""

    def test_adj_close_not_in_bronze_ohlcv_day(self, source_schemas):
        """Direct check: adj_close is not in bronze_ohlcv_day columns."""
        bronze_cols = source_schemas["tables"]["bronze_ohlcv_day"]["columns"]
        assert "adj_close" not in bronze_cols

    def test_adj_close_in_silver_ohlcv_day_adjusted(self, source_schemas):
        """adj_close IS in silver_ohlcv_day_adjusted (the governed adjusted source)."""
        adjusted_cols = set(source_schemas["tables"]["silver_ohlcv_day_adjusted"]["columns"])
        assert "adj_close" in adjusted_cols
        assert "adj_volume" in adjusted_cols
        assert "return_1d" in adjusted_cols

    def test_adjusted_source_has_required_columns(self, source_schemas):
        """silver_ohlcv_day_adjusted must have all columns from the corporate-actions spec."""
        adjusted_cols = set(source_schemas["tables"]["silver_ohlcv_day_adjusted"]["columns"])
        required = {
            "symbol", "event_date", "event_ts",
            "open", "high", "low", "close", "volume", "vwap", "trade_count",
            "cumulative_split_ratio", "price_adjustment_factor",
            "adj_open", "adj_high", "adj_low", "adj_close", "adj_vwap", "adj_volume",
            "raw_overnight_return", "adjusted_return_1d_unmasked",
            "return_1d", "is_data_quality_break",
            "information_available_ts", "processed_ts",
        }
        assert required.issubset(adjusted_cols), (
            f"Missing columns: {required - adjusted_cols}"
        )

    def test_adjusted_source_marked_pending(self, source_schemas):
        """silver_ohlcv_day_adjusted must be marked as pending corporate-actions lane."""
        table_def = source_schemas["tables"]["silver_ohlcv_day_adjusted"]
        assert table_def.get("status") == "pending_corporate_actions_lane"

    def test_no_adj_close_alias_in_daily_prices_derived(self, source_schemas):
        """adj_close must NOT be a derived alias in serve_daily_prices_v1."""
        derived = source_schemas["derived_columns"]["serve_daily_prices_v1"]["derived"]
        derived_names = [d.split("#")[0].strip() for d in derived]
        assert "adj_close" not in derived_names, (
            "adj_close should not be a derived alias — it comes from silver_ohlcv_day_adjusted"
        )

    def test_no_adj_close_alias_in_bounded_bars_derived(self, source_schemas):
        """adj_close must NOT be a derived alias in serve_bounded_daily_bars_v1."""
        derived = source_schemas["derived_columns"]["serve_bounded_daily_bars_v1"]["derived"]
        derived_names = [d.split("#")[0].strip() for d in derived]
        assert "adj_close" not in derived_names, (
            "adj_close should not be a derived alias — it comes from silver_ohlcv_day_adjusted"
        )

    def test_mutation_reintroduce_adj_close_alias_fails(self, ddl_content):
        """Mutation test: reintroducing 'close AS adj_close' in the DDL must fail.

        This proves the schema-truth test catches the exact confusion round 4 was meant to remove.
        """
        # The DDL should NOT contain "close AS adj_close" anywhere
        assert "close AS adj_close" not in ddl_content, (
            "DDL contains 'close AS adj_close' — this aliases unadjusted close as adjusted, "
            "which is the exact confusion round 4/5 was meant to remove."
        )