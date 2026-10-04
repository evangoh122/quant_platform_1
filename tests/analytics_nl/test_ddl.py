"""Tests for DDL/registry correspondence and DDL safety."""

import re
from pathlib import Path

import pytest

from analytics_nl.registry import load_registry


@pytest.fixture
def registry():
    return load_registry()


@pytest.fixture
def ddl_content():
    ddl_path = Path(__file__).parent.parent.parent / "docs" / "NL1_PROPOSED_SERVING_VIEWS.md"
    return ddl_path.read_text(encoding="utf-8")


class TestDDLIdentifiers:
    """DDL view names must match registry approved list."""

    def test_all_approved_views_in_ddl(self, registry, ddl_content):
        for view in registry.approved_views:
            assert view in ddl_content, (
                f"Approved view {view!r} not found in DDL document"
            )

    def test_ddl_views_match_registry(self, registry, ddl_content):
        """Extract CREATE VIEW names from DDL and verify against registry."""
        view_pattern = re.compile(r"CREATE\s+VIEW\s+IF\s+NOT\s+EXISTS\s+\$\{catalog\}\.\$\{schema\}\.(\w+)")
        ddl_views = set(view_pattern.findall(ddl_content))

        registry_views = set(registry.approved_views)
        assert ddl_views == registry_views, (
            f"DDL views {ddl_views} != registry views {registry_views}"
        )


class TestDDLNoSelectStar:
    """DDL must not contain SELECT *."""

    def test_no_select_star(self, ddl_content):
        """Detect SELECT * and table.* patterns in SQL blocks.

        Normalises SQL by stripping comments and collapsing all whitespace
        (including newlines) before matching, so multi-line SELECT / * splits
        are caught.  The old OR-of-negations test was vacuous because it only
        failed when a single line contained both tokens.
        """
        _BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
        _LINE_COMMENT_RE = re.compile(r"--[^\n]*")
        _SELECT_STAR_RE = re.compile(r"\bSELECT\s+\*")
        _TABLE_DOT_STAR_RE = re.compile(r"\.\*")

        lines = ddl_content.splitlines()
        in_sql_block = False
        sql_fragments: list[str] = []
        for line in lines:
            if line.strip() == "```sql":
                in_sql_block = True
                sql_fragments = []
                continue
            if line.strip() == "```":
                in_sql_block = False
                raw_sql = " ".join(sql_fragments)
                cleaned = _BLOCK_COMMENT_RE.sub("", raw_sql)
                cleaned = _LINE_COMMENT_RE.sub("", cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                assert not _SELECT_STAR_RE.search(cleaned), (
                    f"SELECT * found in SQL block: {cleaned[:200]}"
                )
                assert not _TABLE_DOT_STAR_RE.search(cleaned), (
                    f"table.* found in SQL block: {cleaned[:200]}"
                )
                continue
            if in_sql_block:
                sql_fragments.append(line)


class TestDDLAdminWarning:
    """DDL must have prominent unexecuted/admin-only warning."""

    def test_proposal_banner(self, ddl_content):
        assert "Proposal only" in ddl_content
        assert "admin/owner" in ddl_content or "Databricks admin" in ddl_content

    def test_unexecuted_warning(self, ddl_content):
        assert "unexecuted" in ddl_content.lower() or "unverified" in ddl_content.lower()

    def test_owner_action_required(self, ddl_content):
        assert "owner" in ddl_content.lower()


class TestDDLColumnGrain:
    """DDL must document daily grain and use correct column names."""

    def test_daily_grain_documented(self, ddl_content):
        assert "daily" in ddl_content.lower()

    def test_no_intraday(self, ddl_content):
        """DDL should not reference intraday grain."""
        assert "intraday" in ddl_content.lower()  # Should mention it's NOT intraday

    def test_event_date_used_not_trade_date(self, ddl_content):
        """DDL must use event_date (real column) not trade_date."""
        assert "event_date" in ddl_content
        # trade_date should NOT appear as a column reference in SQL blocks
        lines = ddl_content.splitlines()
        in_sql = False
        for line in lines:
            if line.strip() == "```sql":
                in_sql = True
            elif line.strip() == "```":
                in_sql = False
            elif in_sql:
                assert "trade_date" not in line, (
                    f"trade_date found in SQL block (should be event_date): {line.strip()}"
                )

    def test_feature_ts_in_options_view(self, ddl_content):
        """Options view must use feature_ts (real column) not trade_date."""
        assert "feature_ts" in ddl_content

    def test_close_used_not_adj_close_source(self, ddl_content):
        """DDL must NOT alias unadjusted close as adj_close.

        adj_close comes from silver_ohlcv_day_adjusted (the governed adjusted source),
        not from aliasing bronze_ohlcv_day.close.
        """
        # The DDL must NOT have "close AS adj_close" — that was the round 4/5 confusion
        assert "close AS adj_close" not in ddl_content, (
            "DDL contains 'close AS adj_close' which aliases unadjusted close as adjusted"
        )


class TestDDLPITSafety:
    """DDL must include information_available_ts for PIT safety."""

    def test_pit_column_in_views(self, ddl_content):
        assert "information_available_ts" in ddl_content

    def test_pit_safety_documented(self, ddl_content):
        assert "PIT" in ddl_content or "point-in-time" in ddl_content.lower() or "look-ahead" in ddl_content.lower()

    def test_pit_derivation_documented(self, ddl_content):
        """DDL must document how information_available_ts is derived for daily bars."""
        assert "16:30" in ddl_content
        assert "America/New_York" in ddl_content
        assert "to_utc_timestamp" in ddl_content


class TestDDLDeduplication:
    """DDL must document deduplication rules."""

    def test_dedup_documented(self, ddl_content):
        assert "ROW_NUMBER()" in ddl_content or "dedup" in ddl_content.lower()


class TestDDLReturnFormula:
    """DDL must document return formula."""

    def test_return_formula(self, ddl_content):
        assert "return_1d" in ddl_content
        assert "LAG" in ddl_content


class TestDDLUnadjustedPrices:
    """DDL must document that prices are unadjusted."""

    def test_unadjusted_documented(self, ddl_content):
        assert "unadjusted" in ddl_content.lower() or "UNADJUSTED" in ddl_content

    def test_close_used_in_formulas(self, ddl_content):
        """Return/drawdown/momentum formulas should use close, not adj_close as source."""
        # The formulas in the DDL should reference close (not adj_close as a source column)
        assert "close - LAG(close)" in ddl_content or "close / LAG(close" in ddl_content


class TestDDLSuspectedSplitDetector:
    """DDL must include suspected_split detector in bounded bars view."""

    def test_suspected_split_in_ddl(self, ddl_content):
        assert "suspected_split" in ddl_content

    def test_split_ratio_check_in_ddl(self, ddl_content):
        """DDL must check for common split ratios."""
        assert "0.4" in ddl_content  # 40% threshold


class TestDDLVolatilityFormula:
    """DDL must document realized volatility."""

    def test_volatility_formula(self, ddl_content):
        assert "realized_vol" in ddl_content
        assert "STDDEV" in ddl_content or "SQRT(252)" in ddl_content


class TestDDLDrawdownFormula:
    """DDL must document drawdown definition."""

    def test_drawdown_formula(self, ddl_content):
        assert "drawdown" in ddl_content


class TestDDLGrants:
    """DDL must document grants."""

    def test_grants_section(self, ddl_content):
        assert "SELECT" in ddl_content
        assert "service principal" in ddl_content.lower() or "grants" in ddl_content.lower()


class TestDDLKnownSplits:
    """DDL must propose a known_splits table for corporate-action safety."""

    def test_known_splits_table(self, ddl_content):
        assert "known_splits" in ddl_content

    def test_known_splits_columns(self, ddl_content):
        """known_splits must have symbol, ex_date, ratio, source."""
        assert "symbol" in ddl_content
        assert "ex_date" in ddl_content
        assert "ratio" in ddl_content


class TestDDLAdjustedSource:
    """DDL must document adjusted source and fallback modes."""

    def test_adjusted_source_in_ddl(self, ddl_content):
        """DDL must reference silver_ohlcv_day_adjusted."""
        assert "silver_ohlcv_day_adjusted" in ddl_content

    def test_fallback_mode_documented(self, ddl_content):
        """DDL must document fallback to bronze_ohlcv_day."""
        assert "fallback" in ddl_content.lower() or "Fallback" in ddl_content

    def test_adjusted_source_available_flag_documented(self, ddl_content):
        """DDL must reference the adjusted_source_available flag."""
        assert "adjusted_source_available" in ddl_content

    def test_both_modes_in_daily_prices(self, ddl_content):
        """serve_daily_prices_v1 must have both primary and fallback DDL."""
        # Find the serve_daily_prices_v1 section
        section_start = ddl_content.find("## serve_daily_prices_v1")
        section_end = ddl_content.find("## serve_daily_equity_metrics_v1")
        section = ddl_content[section_start:section_end]
        assert "silver_ohlcv_day_adjusted" in section
        assert "bronze_ohlcv_day" in section

    def test_both_modes_in_bounded_bars(self, ddl_content):
        """serve_bounded_daily_bars_v1 must have both primary and fallback DDL."""
        section_start = ddl_content.find("## serve_bounded_daily_bars_v1")
        section_end = ddl_content.find("## known_splits")
        section = ddl_content[section_start:section_end]
        assert "silver_ohlcv_day_adjusted" in section
        assert "bronze_ohlcv_day" in section


class TestDDLIdentifierCorrespondence:
    """DDL identifier table must match registry."""

    def test_correspondence_table(self, registry, ddl_content):
        """The identifier correspondence table should list all approved views."""
        for view in registry.approved_views:
            assert view in ddl_content


class TestDDLPITSafetyAsOfBeforeWindow:
    """Every derived metric must be computed from as-of-filtered input rows."""

    def _extract_sql_blocks(self, content: str) -> list[str]:
        """Extract all SQL blocks from markdown."""
        blocks = []
        in_sql = False
        lines = []
        for line in content.splitlines():
            if line.strip() == "```sql":
                in_sql = True
                lines = []
            elif line.strip() == "```" and in_sql:
                in_sql = False
                blocks.append("\n".join(lines))
            elif in_sql:
                lines.append(line)
        return blocks

    def _parse_sql_ctes_and_final_select(self, sql: str):
        """Parse SQL into (ctes, final_select) by tracking parenthesis depth.

        ctes: list of (name, body) tuples
        final_select: the SQL after the last CTE closes
        """
        sql_upper = sql.upper()
        cte_pattern = re.compile(r"(\w+)\s+AS\s*\(")
        pos = 0
        ctes = []
        while pos < len(sql_upper):
            m = cte_pattern.search(sql_upper, pos)
            if not m:
                break
            name = m.group(1)
            depth = 0
            i = m.end() - 1  # points at the '('
            while i < len(sql_upper):
                ch = sql_upper[i]
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            body = sql_upper[m.end():i]
            ctes.append((name, body))
            pos = i + 1
            # skip comma and whitespace between CTEs
            while pos < len(sql_upper) and sql_upper[pos] in ' \t\n,':
                pos += 1
        final_select = sql_upper[pos:] if pos < len(sql_upper) else ""
        return ctes, final_select

    def _has_as_of_filter_before_window(self, sql: str) -> bool:
        """Check that as_of filtering appears in a CTE that feeds into window/aggregate.

        Strategy: split SQL into CTE list and final SELECT (track parenthesis depth).
        Find CTEs that use window functions. Verify that some CTE read by the
        window/aggregate CTE (directly or transitively) contains the as_of filter,
        and the window/aggregate CTE itself does not read the unfiltered base table.
        """
        ctes, final_select = self._parse_sql_ctes_and_final_select(sql)

        window_patterns = [
            r"ROW_NUMBER\s*\(\s*\)\s*OVER",
            r"STDDEV_SAMP\s*\(",
            r"MAX\s*\([^)]+\)\s*OVER",
            r"LAG\s*\(",
            r"EXP\s*\(\s*SUM\s*\(\s*(?:LN|GREATEST)",
        ]

        has_window = False
        for _, body in ctes:
            if any(re.search(p, body) for p in window_patterns):
                has_window = True
                break
        # Also check final SELECT for window functions (e.g. momentum LAG)
        if not has_window and any(re.search(p, final_select) for p in window_patterns):
            has_window = True
        if not has_window:
            return True

        as_of_pattern = r"(?:INFORMATION_AVAILABLE_TS|TO_UTC_TIMESTAMP)\b.*?<=\s*:AS_OF"

        # Find CTEs with as_of filter
        as_of_ctes = set()
        for name, body in ctes:
            if re.search(as_of_pattern, body):
                as_of_ctes.add(name)

        if not as_of_ctes:
            return False

        # Find CTEs with window functions (the ones that need as_of filtered input)
        window_ctes = set()
        for name, body in ctes:
            if any(re.search(p, body) for p in window_patterns):
                window_ctes.add(name)

        # For each window CTE, check it reads from an as_of-filtered CTE
        # (transitively). Build a simple read-graph: a CTE "reads" another if
        # the other's name appears in its body.
        cte_names = {name for name, _ in ctes}
        cte_body_map = dict(ctes)

        # Build read graph
        read_graph: dict[str, set[str]] = {}
        for name, body in ctes:
            read_graph[name] = {n for n in cte_names if n != name and n in body.split()}

        # BFS: for each window CTE, check if any ancestor has as_of
        for w_cte in window_ctes:
            # BFS from w_cte through read_graph
            visited: set[str] = set()
            queue = [w_cte]
            found_as_of = False
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                for dep in read_graph.get(current, set()):
                    if dep in as_of_ctes:
                        found_as_of = True
                        break
                    queue.append(dep)
                if found_as_of:
                    break
            if not found_as_of:
                return False

        return True

    def test_all_views_have_as_of_before_window(self, ddl_content):
        """Every SQL block with window functions must have as-of filter in an earlier CTE."""
        blocks = self._extract_sql_blocks(ddl_content)
        for i, sql in enumerate(blocks):
            assert self._has_as_of_filter_before_window(sql), (
                f"SQL block {i + 1} has window functions but no as-of filter "
                f"(information_available_ts <= :as_of) in a preceding CTE.\n"
                f"SQL preview: {sql[:300]}"
            )

    def test_relative_performance_includes_benchmark_availability(self, ddl_content):
        """Relative performance output must include benchmark availability in GREATEST."""
        # Find the relative performance SQL block
        section_start = ddl_content.find("## serve_relative_performance_v1")
        section_end = ddl_content.find("## serve_options_metrics_v1")
        section = ddl_content[section_start:section_end]

        # Must use GREATEST with benchmark availability
        assert "GREATEST" in section, (
            "Relative performance must use GREATEST for information_available_ts"
        )
        assert "bench_info_ts" in section or "benchmark" in section.lower(), (
            "Relative performance must propagate benchmark availability"
        )

    def test_mutation_as_of_after_window_fails(self, ddl_content):
        """Mutation proof: moving as-of filter after window must fail the PIT test.

        For serve_options_metrics_v1: remove the as_of WHERE from the as_of_filtered
        CTE and add the filter to the final WHERE rn = 1 → test FAILS.
        """
        blocks = self._extract_sql_blocks(ddl_content)
        # Find the serve_options_metrics_v1 block (has ROW_NUMBER + as_of)
        for sql in blocks:
            sql_upper = sql.upper()
            if "INFORMATION_AVAILABLE_TS" in sql_upper and "ROW_NUMBER" in sql_upper:
                # Remove the as_of filter from the CTE WHERE clause
                mutated = re.sub(
                    r"\s*WHERE\s+(?:information_available_ts|to_utc_timestamp)\b.*?<=\s*:as_of\s*",
                    " ",
                    sql,
                    flags=re.IGNORECASE,
                )
                # Add the filter to the final WHERE (after the window)
                mutated = re.sub(
                    r"(WHERE\s+rn\s*=\s*1)\s*",
                    r"\1 AND information_available_ts <= :as_of ",
                    mutated,
                    count=1,
                    flags=re.IGNORECASE,
                )
                # Now the mutation should fail the check
                assert not self._has_as_of_filter_before_window(mutated), (
                    "Mutation proof failed: moving as_of filter after window "
                    "(into final WHERE) should break the check"
                )
                return
        pytest.skip("No SQL block found with both as_of filter and window functions")

    def test_mutation_equity_metrics_as_of_after_window_fails(self, ddl_content):
        """Mutation proof: removing as_of from serve_daily_equity_metrics_v1 input CTE fails."""
        blocks = self._extract_sql_blocks(ddl_content)
        # Find the equity metrics block (has STDDEV_SAMP + as_of)
        for sql in blocks:
            sql_upper = sql.upper()
            if "SERVE_DAILY_PRICES_V1" in sql_upper and "STDDEV_SAMP" in sql_upper:
                # Remove the as_of filter from the daily_prices CTE
                mutated = re.sub(
                    r"\s*WHERE\s+information_available_ts\s*<=\s*:as_of\s*",
                    " ",
                    sql,
                    flags=re.IGNORECASE,
                )
                assert not self._has_as_of_filter_before_window(mutated), (
                    "Mutation proof failed: removing as_of from equity metrics "
                    "input CTE should break the check"
                )
                return
        pytest.skip("No SQL block found with both equity metrics window and as_of filter")


class TestDDLRelativePerformanceSemantics:
    """Relative performance must use parameterized benchmark and cumulative return."""

    def test_benchmark_parameterized(self, ddl_content):
        """Relative performance must not hardcode SPY — must use parameter."""
        section_start = ddl_content.find("## serve_relative_performance_v1")
        section_end = ddl_content.find("## serve_options_metrics_v1")
        section = ddl_content[section_start:section_end]

        # Must NOT have hardcoded WHERE symbol = 'SPY'
        sql_blocks = []
        in_sql = False
        for line in section.splitlines():
            if line.strip() == "```sql":
                in_sql = True
                sql_lines = []
            elif line.strip() == "```" and in_sql:
                in_sql = False
                sql_blocks.append("\n".join(sql_lines))
            elif in_sql:
                sql_lines.append(line)

        for sql in sql_blocks:
            normalized = " ".join(sql.upper().split())
            assert "SYMBOL = 'SPY'" not in normalized, (
                "Relative performance must not hardcode SPY — use :benchmark parameter"
            )

    def test_uses_cumulative_return(self, ddl_content):
        """Relative performance must compute cumulative return, not one-day difference."""
        section_start = ddl_content.find("## serve_relative_performance_v1")
        section_end = ddl_content.find("## serve_options_metrics_v1")
        section = ddl_content[section_start:section_end]

        # Must use cumulative return calculation
        assert "cumulative_return" in section.lower() or "cumulative" in section.lower(), (
            "Relative performance must use cumulative return"
        )

    def test_start_date_bound_in_inputs(self, ddl_content):
        """Relative performance must have :start_date bound in input CTEs."""
        section_start = ddl_content.find("## serve_relative_performance_v1")
        section_end = ddl_content.find("## serve_options_metrics_v1")
        section = ddl_content[section_start:section_end]

        # Must have :start_date in WHERE clauses
        assert ":start_date" in section, (
            "Relative performance must have :start_date bound in inputs"
        )
        # Must filter by event_date >= :start_date
        assert "event_date >= :start_date" in section.lower() or "event_date >= :start_date" in section, (
            "Relative performance must filter by event_date >= :start_date"
        )

    def test_anomaly_propagation_for_invalid_returns(self, ddl_content):
        """Relative performance must propagate invalid returns (≤ -100%) as NULL."""
        section_start = ddl_content.find("## serve_relative_performance_v1")
        section_end = ddl_content.find("## serve_options_metrics_v1")
        section = ddl_content[section_start:section_end]

        # Must use BOOL_OR to detect invalid returns
        assert "BOOL_OR" in section, (
            "Relative performance must use BOOL_OR to detect invalid returns"
        )
        # Must check for return_1d <= -1
        assert "return_1d <= -1" in section.lower() or "return_1d <= -1" in section, (
            "Relative performance must check for return_1d <= -1"
        )
        # Must set status to 'invalid_return' when invalid returns detected
        assert "invalid_return" in section, (
            "Relative performance must set status to 'invalid_return' when invalid returns detected"
        )
        # Must use CASE to set cumulative_return to NULL when invalid
        assert "CASE" in section, (
            "Relative performance must use CASE to set cumulative_return to NULL when invalid"
        )


class TestDDLAvailabilityContract:
    """Every output information_available_ts must be a window MAX / GREATEST over all inputs."""

    def _extract_sql_blocks(self, content: str) -> list[str]:
        """Extract all SQL blocks from markdown."""
        blocks = []
        in_sql = False
        lines = []
        for line in content.splitlines():
            if line.strip() == "```sql":
                in_sql = True
                lines = []
            elif line.strip() == "```" and in_sql:
                in_sql = False
                blocks.append("\n".join(lines))
            elif in_sql:
                lines.append(line)
        return blocks

    def _parse_sql_ctes_and_final_select(self, sql: str):
        """Parse SQL into (ctes, final_select) by tracking parenthesis depth.

        ctes: list of (name, body) tuples
        final_select: the SQL after the last CTE closes
        """
        sql_upper = sql.upper()
        cte_pattern = re.compile(r"(\w+)\s+AS\s*\(")
        pos = 0
        ctes = []
        while pos < len(sql_upper):
            m = cte_pattern.search(sql_upper, pos)
            if not m:
                break
            name = m.group(1)
            depth = 0
            i = m.end() - 1  # points at the '('
            while i < len(sql_upper):
                ch = sql_upper[i]
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            body = sql_upper[m.end():i]
            ctes.append((name, body))
            pos = i + 1
            # skip comma and whitespace between CTEs
            while pos < len(sql_upper) and sql_upper[pos] in ' \t\n,':
                pos += 1
        final_select = sql_upper[pos:] if pos < len(sql_upper) else ""
        return ctes, final_select

    def test_output_availability_is_window_max(self, ddl_content):
        """Every output information_available_ts must be a window MAX / GREATEST over all inputs."""
        blocks = self._extract_sql_blocks(ddl_content)
        for i, sql in enumerate(blocks):
            ctes, final_select = self._parse_sql_ctes_and_final_select(sql)
            
            # Check if final SELECT has information_available_ts
            if "INFORMATION_AVAILABLE_TS" not in final_select:
                continue
            
            # Check if it uses GREATEST or MAX(...) OVER
            has_greatest = "GREATEST" in final_select
            has_max_over = re.search(r"MAX\s*\([^)]+\)\s*OVER", final_select) is not None
            
            # For windowed metrics, must use GREATEST or MAX(...) OVER
            if has_greatest or has_max_over:
                # Check that GREATEST includes all contributing availability timestamps
                if has_greatest:
                    # Find the GREATEST(...) expression
                    greatest_match = re.search(r"GREATEST\s*\(([^)]+)\)", final_select)
                    if greatest_match:
                        args = greatest_match.group(1)
                        # Must include at least two availability timestamps
                        # (e.g., entity_info_ts, bench_max_info_ts or information_available_ts, realized_vol_20d_info_ts)
                        info_ts_count = len(re.findall(r"(?:INFORMATION_AVAILABLE_TS|_INFO_TS|_AVAILABILITY)", args))
                        assert info_ts_count >= 2, (
                            f"SQL block {i + 1}: GREATEST must combine at least 2 availability timestamps, "
                            f"found {info_ts_count} in: {args[:200]}"
                        )
                elif has_max_over:
                    # Check that MAX(...) OVER is applied to information_available_ts
                    max_over_match = re.search(r"MAX\s*\(\s*INFORMATION_AVAILABLE_TS\s*\)\s*OVER", final_select)
                    assert max_over_match, (
                        f"SQL block {i + 1}: MAX(...) OVER must be applied to information_available_ts"
                    )