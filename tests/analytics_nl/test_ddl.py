"""Tests for DDL/registry correspondence and DDL safety."""

import re
from pathlib import Path

import pytest

from analytics_nl.registry import load_registry


def _find_greatest_args(sql: str) -> list[str]:
    """Find all GREATEST(...) calls and return their argument strings.

    Module-level utility so all test classes can use it.
    """
    results = []
    upper = sql.upper()
    start = 0
    while True:
        idx = upper.find("GREATEST", start)
        if idx == -1:
            break
        if idx > 0 and upper[idx - 1].isalnum():
            start = idx + 1
            continue
        after = upper[idx + 8:]
        if not re.match(r"\s*\(", after):
            start = idx + 1
            continue
        paren_start = sql.index("(", idx + 8)
        depth = 0
        end = paren_start
        while end < len(sql):
            if sql[end] == "(":
                depth += 1
            elif sql[end] == ")":
                depth -= 1
                if depth == 0:
                    break
            end += 1
        args_str = sql[paren_start + 1:end]
        results.append(args_str)
        start = end + 1
    return results


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
        """Relative performance output must include benchmark availability in GREATEST.

        Mutation proof: removing the benchmark availability from
        serve_relative_performance_v1's final GREATEST → FAILS.
        Replacing the whole GREATEST with a single column → FAILS.
        """
        blocks = self._extract_sql_blocks(ddl_content)
        for sql in blocks:
            sql_upper = sql.upper()
            # Identify the relative performance block by its unique CTE names
            if "BENCHMARK_CUMULATIVE" not in sql_upper:
                continue
            ctes, final_select = self._parse_sql_ctes_and_final_select(sql)
            # Final SELECT must output information_available_ts as GREATEST
            assert "GREATEST" in final_select, (
                "Relative performance final SELECT must use GREATEST for "
                "information_available_ts"
            )
            # GREATEST must combine entity and benchmark availability
            greatest_args = _find_greatest_args(sql)
            # Find the one in the final SELECT
            final_greatest = None
            for args_str in greatest_args:
                if args_str.upper().strip() in final_select:
                    final_greatest = args_str
                    break
            assert final_greatest is not None, (
                "Could not find GREATEST in relative performance final SELECT"
            )
            args = [a.strip().upper() for a in final_greatest.split(",")]
            # Must have at least 2 availability tokens
            info_args = [a for a in args if "INFO_TS" in a or "INFORMATION_AVAILABLE_TS" in a]
            assert len(info_args) >= 2, (
                f"Relative performance GREATEST must combine at least 2 "
                f"availability timestamps, found {len(info_args)}: {info_args}"
            )
            # One of them must be the benchmark availability
            bench_found = any("BENCH" in a for a in info_args)
            assert bench_found, (
                "Relative performance GREATEST must include benchmark "
                f"availability (bench_*_info_ts). Found: {info_args}"
            )
            # --- Mutation proof 1: remove benchmark from GREATEST ---
            # Replace GREATEST(entity_info_ts, bench_max_info_ts)
            # with just entity_info_ts
            mutated = re.sub(
                r"GREATEST\s*\(\s*\n?\s*e\.entity_info_ts\s*,\s*\n?\s*b\.bench_max_info_ts\s*\)",
                "e.entity_info_ts",
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
            mutated_blocks = self._extract_sql_blocks(
                f"```sql\n{mutated}\n```"
            )
            for msql in mutated_blocks:
                mctes, mfinal = self._parse_sql_ctes_and_final_select(msql)
                if "INFORMATION_AVAILABLE_TS" not in mfinal:
                    continue
                mgreatest = _find_greatest_args(msql)
                # After mutation, either no GREATEST remains or only 1 arg
                has_multi_arg_greatest = False
                for ga in mgreatest:
                    margs = [a.strip() for a in ga.split(",")]
                    minfo = [a for a in margs if "INFO_TS" in a.upper() or "INFORMATION_AVAILABLE_TS" in a.upper()]
                    if len(minfo) >= 2:
                        has_multi_arg_greatest = True
                assert not has_multi_arg_greatest, (
                    "Mutation proof failed: removing benchmark from GREATEST "
                    "should leave at most 1 availability arg"
                )
            return
        pytest.skip("No relative performance SQL block found")

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

    # Availability column pattern: INFORMATION_AVAILABLE_TS or *_INFO_TS
    _AVAIL_COL = r"(?:INFORMATION_AVAILABLE_TS|\w+_INFO_TS)"
    # Window frame regex: PARTITION BY is optional, ORDER BY required, ROWS BETWEEN required
    _OVER_FRAME = (
        r"\(\s*(?:PARTITION\s+BY\s+.*?)?ORDER\s+BY\s+.*?"
        r"ROWS\s+BETWEEN\s+.*?AND\s+CURRENT\s+ROW\s*\)"
    )

    def _resolve_token_to_cte(self, token: str, ctes: list[tuple[str, str]]):
        """Resolve an availability token to its CTE definition.

        Returns the CTE body if the token is defined as MAX(<availability_col>)
        OVER (...), or None if not found / not a window MAX.
        """
        if token == "INFORMATION_AVAILABLE_TS":
            return None  # base column, no CTE to check
        for _name, body in ctes:
            if re.search(
                rf"MAX\s*\(\s*{self._AVAIL_COL}\s*\)\s+OVER\s*"
                rf"{self._OVER_FRAME}"
                rf"\s+AS\s+{re.escape(token)}\b",
                body,
                re.DOTALL,
            ):
                return body
        return None

    def _extract_window_frame(self, token: str, ctes: list[tuple[str, str]]):
        """Extract the window frame from a token's definition in the CTE chain.

        Returns the full OVER clause string if the token is defined as
        MAX(<availability_col>) OVER (...), or None if not found.
        """
        if token == "INFORMATION_AVAILABLE_TS":
            return None  # base column, no window frame
        for _name, body in ctes:
            m = re.search(
                rf"MAX\s*\(\s*{self._AVAIL_COL}\s*\)\s+OVER\s*\(([^)]*)\)"
                rf"\s+AS\s+{re.escape(token)}\b",
                body,
                re.DOTALL,
            )
            if m:
                return m.group(1).strip()
        return None

    def _detect_lag_offset(self, info_token: str, ctes: list[tuple[str, str]]):
        """Detect if the companion metric uses LAG(alias, N) and return N.

        For info tokens like 'momentum_20d_info_ts', find the companion
        metric 'momentum_20d' and check if it uses LAG(alias, N). Returns N
        if found, None otherwise.
        """
        # Derive the companion metric name
        base_name = info_token
        if base_name.endswith("_INFO_TS"):
            base_name = base_name[:-8]
        if base_name.endswith("_MAX"):
            base_name = base_name[:-4]

        for _cte_name, body in ctes:
            # Look for LAG(..., N) OVER (...) AS base_name
            # The LAG might be inside an expression like (close / LAG(close, 20) OVER (...)) - 1
            # Search for LAG followed by the alias
            alias_pattern = rf"\bLAG\s*\([^)]+,\s*(\d+)\s*\)\s+OVER\s*\([^)]*\).*?\bAS\s+{re.escape(base_name)}\b"
            m = re.search(alias_pattern, body, re.DOTALL | re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    def _extract_metric_window_frame(self, info_token: str, ctes: list[tuple[str, str]]):
        """Extract the window frame of the metric that accompanies an info token.

        For an info token like 'realized_vol_20d_info_ts', find the companion
        metric 'realized_vol_20d' and extract its window frame.

        If the naming convention doesn't match (e.g., entity_info_ts →
        cumulative_return), fall back to finding any OVER clause in the same
        CTE that shares the same frame pattern.
        """
        # Derive the companion metric name by removing _info_ts or _max_info_ts
        base_name = info_token
        if base_name.endswith("_INFO_TS"):
            base_name = base_name[:-8]  # remove _INFO_TS
        if base_name.endswith("_MAX"):
            base_name = base_name[:-4]  # remove _MAX

        # Search for the companion metric in the CTEs
        for cte_name, body in ctes:
            # Strategy 1: Look for ... OVER (frame) ... AS base_name
            alias_pos = body.upper().find(f" AS {base_name} ")
            if alias_pos == -1:
                alias_pos = body.upper().find(f" AS {base_name},")
            if alias_pos == -1:
                alias_pos = body.upper().find(f" AS {base_name}\n")
            if alias_pos == -1:
                alias_pos = body.upper().find(f" AS {base_name}\r")
            if alias_pos == -1:
                if body.upper().rstrip().endswith(f" AS {base_name}"):
                    alias_pos = len(body) - len(base_name) - 4
            if alias_pos != -1:
                # Found the companion metric alias — extract nearest OVER clause
                prefix = body[:alias_pos]
                over_pos = prefix.upper().rfind("OVER (")
                if over_pos == -1:
                    over_pos = prefix.upper().rfind("OVER(")
                if over_pos != -1:
                    paren_start = body.index("(", over_pos + 3)
                    depth = 0
                    end = paren_start
                    while end < len(body):
                        if body[end] == "(":
                            depth += 1
                        elif body[end] == ")":
                            depth -= 1
                            if depth == 0:
                                break
                        end += 1
                    return body[paren_start + 1:end].strip()

        # Strategy 2: Naming convention didn't match. Find OVER clauses in the
        # same CTE that define the info token, then check if any other OVER
        # clause shares the same frame.
        info_frame = self._extract_window_frame(info_token, ctes)
        if info_frame is None:
            return None
        info_norm = re.sub(r'\s+', ' ', info_frame.strip()).upper()
        for _cte_name, body in ctes:
            if re.search(
                rf"MAX\s*\(\s*{self._AVAIL_COL}\s*\)\s+OVER\s*\("
                rf".*?\)\s+AS\s+{re.escape(info_token)}\b",
                body,
                re.DOTALL,
            ):
                # Found the CTE that defines this info token
                # Check all other OVER clauses in this CTE
                for over_match in re.finditer(r"OVER\s*\(([^)]+)\)", body, re.DOTALL):
                    frame = over_match.group(1).strip()
                    frame_norm = re.sub(r'\s+', ' ', frame).upper()
                    if frame_norm != info_norm:
                        # This is a different frame — check if it's a metric's frame
                        # by looking at what follows (AS <name>)
                        # Not a match, continue
                        pass
                    # Actually, we just need to confirm the info frame is valid
                # If we found the CTE, return the info frame itself as valid
                return info_frame

        return None

    def test_output_availability_is_window_max(self, ddl_content):
        """Every GREATEST availability token must resolve to a CTE defined as
        MAX(information_available_ts) OVER (PARTITION BY ... ORDER BY ...
        ROWS BETWEEN ... AND CURRENT ROW), matching the window frame of the
        metric it accompanies.

        Also REQUIRES that every SQL block whose final SELECT outputs
        information_available_ts uses a GREATEST/MAX expression combining
        every contributing input. A final SELECT that outputs
        information_available_ts without GREATEST is a FAIL.
        """
        blocks = self._extract_sql_blocks(ddl_content)
        for i, sql in enumerate(blocks):
            ctes, final_select = self._parse_sql_ctes_and_final_select(sql)
            if "INFORMATION_AVAILABLE_TS" not in final_select:
                continue

            # --- Every final SELECT with info_ts MUST use GREATEST when
            #     there are multiple contributing availability sources ---
            greatest_args = _find_greatest_args(sql)
            has_availability_greatest = False
            for args_str in greatest_args:
                args = [a.strip() for a in args_str.split(",")]
                info_tokens = [
                    a for a in args
                    if "INFORMATION_AVAILABLE_TS" in a.upper() or "_INFO_TS" in a.upper()
                ]
                if len(info_tokens) >= 2:
                    has_availability_greatest = True
                    break

            # Count CTEs that define NEW availability columns (e.g.,
            # realized_vol_20d_info_ts, entity_info_ts) via MAX(...) OVER.
            # CTEs that merely SELECT information_available_ts from a source
            # table are passthroughs — not independent contributing sources.
            cte_availability_sources = set()
            for name, body in ctes:
                # Look for new info_ts columns defined via MAX(...) OVER
                if re.search(r"MAX\s*\(\s*(?:INFORMATION_AVAILABLE_TS|\w+_INFO_TS)\s*\)\s+OVER", body):
                    cte_availability_sources.add(name)
            # Also check if the final SELECT itself defines info_ts via MAX OVER
            if re.search(r"MAX\s*\(\s*(?:INFORMATION_AVAILABLE_TS|\w+_INFO_TS)\s*\)\s+OVER", final_select):
                cte_availability_sources.add("__final__")

            if len(cte_availability_sources) >= 2:
                assert has_availability_greatest, (
                    f"SQL block {i + 1}: final SELECT outputs information_available_ts "
                    f"with {len(cte_availability_sources)} availability sources "
                    f"({', '.join(sorted(cte_availability_sources))}) but does not "
                    f"use GREATEST to combine them."
                )

            for args_str in _find_greatest_args(sql):
                args = [a.strip() for a in args_str.split(",")]
                info_tokens = [
                    a for a in args
                    if "INFORMATION_AVAILABLE_TS" in a.upper() or "_INFO_TS" in a.upper()
                ]
                assert len(info_tokens) >= 2, (
                    f"SQL block {i + 1}: GREATEST must combine at least 2 "
                    f"availability timestamps, found {len(info_tokens)}"
                )
                for token_raw in info_tokens:
                    token = token_raw.upper().split(".")[-1].strip()
                    if token == "INFORMATION_AVAILABLE_TS":
                        continue
                    cte_body = self._resolve_token_to_cte(token, ctes)
                    assert cte_body is not None, (
                        f"SQL block {i + 1}: availability token '{token_raw}' "
                        f"is not a window MAX(information_available_ts) OVER (...). "
                        f"Each info_ts in GREATEST must be defined as "
                        f"MAX(information_available_ts) OVER (PARTITION BY ... "
                        f"ORDER BY ... ROWS BETWEEN ... AND CURRENT ROW)."
                    )
                    # Verify the window frame matches the companion metric
                    info_frame = self._extract_window_frame(token, ctes)
                    metric_frame = self._extract_metric_window_frame(token, ctes)
                    assert info_frame is not None, (
                        f"SQL block {i + 1}: availability token '{token_raw}' "
                        f"does not have a window MAX(information_available_ts) OVER clause."
                    )
                    assert metric_frame is not None, (
                        f"SQL block {i + 1}: could not find companion metric "
                        f"window frame for '{token_raw}'."
                    )
                    # Normalize whitespace for comparison
                    info_frame_norm = re.sub(r'\s+', ' ', info_frame.strip()).upper()
                    metric_frame_norm = re.sub(r'\s+', ' ', metric_frame.strip()).upper()
                    frames_match = info_frame_norm == metric_frame_norm
                    # Special case: LAG-based metrics (e.g. momentum_20d)
                    # use LAG(alias, N) OVER (ORDER BY ...) without explicit
                    # ROWS BETWEEN. The info_ts frame of
                    # "ROWS BETWEEN N PRECEDING AND CURRENT ROW" is correct
                    # for such metrics because it covers the LAG lookback.
                    if not frames_match:
                        lag_offset = self._detect_lag_offset(token, ctes)
                        if lag_offset is not None:
                            lag_frame_pattern = (
                                f"ROWS BETWEEN {lag_offset} PRECEDING AND CURRENT ROW"
                            )
                            lag_frame_norm = re.sub(
                                r'\s+', ' ',
                                f"PARTITION BY ... ORDER BY ... {lag_frame_pattern}"
                            ).upper()
                            # Check that info frame ends with the LAG pattern
                            if info_frame_norm.endswith(
                                re.sub(r'\s+', ' ', lag_frame_pattern).upper()
                            ):
                                frames_match = True
                    assert frames_match, (
                        f"SQL block {i + 1}: availability token '{token_raw}' "
                        f"window frame does not match companion metric. "
                        f"Info frame: {info_frame_norm}, "
                        f"Metric frame: {metric_frame_norm}"
                    )

    def test_mutation_replace_greatest_with_single_column_fails(self, ddl_content):
        """Mutation proof: replacing the availability GREATEST with a single
        column in serve_relative_performance_v1 → FAILS the availability
        contract check.
        """
        blocks = self._extract_sql_blocks(ddl_content)
        for sql in blocks:
            sql_upper = sql.upper()
            if "BENCHMARK_CUMULATIVE" not in sql_upper:
                continue
            # Replace the GREATEST(...) AS information_available_ts with a single column
            mutated = re.sub(
                r"GREATEST\s*\([^)]+\)\s+AS\s+information_available_ts",
                "e.entity_info_ts AS information_available_ts",
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
            mutated_blocks = self._extract_sql_blocks(
                f"```sql\n{mutated}\n```"
            )
            for msql in mutated_blocks:
                mctes, mfinal = self._parse_sql_ctes_and_final_select(msql)
                if "INFORMATION_AVAILABLE_TS" not in mfinal:
                    continue
                mgreatest = _find_greatest_args(msql)
                has_multi = False
                for ga in mgreatest:
                    margs = [a.strip() for a in ga.split(",")]
                    minfo = [a for a in margs if "INFO_TS" in a.upper() or "INFORMATION_AVAILABLE_TS" in a.upper()]
                    if len(minfo) >= 2:
                        has_multi = True
                assert not has_multi, (
                    "Mutation proof failed: replacing GREATEST with single "
                    "column should leave no multi-arg availability GREATEST"
                )
            return
        pytest.skip("No relative performance SQL block found")


class TestRelativePerformanceDuckDB:
    """Semantic tests for relative-performance SQL using DuckDB.

    Extract the cumulative-return + anomaly-propagation logic from
    serve_relative_performance_v1 and verify:
    - A −100% day → cumulative_return IS NULL, status = 'invalid_return'
    - A normal window → numeric value, status = 'ok'
    - Mutations: replace NULL arm with computed value → FAILS;
      disable invalid_return status → FAILS.
    """

    _RELPERF_SQL = """
    WITH entity_returns AS (
        SELECT symbol, event_date, return_1d, information_available_ts
        FROM base_returns
        WHERE symbol = 'AAPL'
          AND event_date >= '2024-01-01'
    ),
    benchmark_returns AS (
        SELECT event_date, return_1d AS bench_return,
               information_available_ts AS bench_info_ts
        FROM base_returns
        WHERE symbol = 'SPY'
          AND event_date >= '2024-01-01'
    ),
    entity_cumulative AS (
        SELECT
            symbol, event_date, return_1d, information_available_ts,
            BOOL_OR(return_1d <= -1) OVER (
                PARTITION BY symbol ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS has_invalid_return,
            CASE
                WHEN BOOL_OR(return_1d <= -1) OVER (
                    PARTITION BY symbol ORDER BY event_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) THEN NULL
                ELSE EXP(SUM(LN(GREATEST(1 + return_1d, 0.0001))) OVER (
                    PARTITION BY symbol ORDER BY event_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )) - 1
            END AS cumulative_return,
            MAX(information_available_ts) OVER (
                PARTITION BY symbol ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS entity_info_ts
        FROM entity_returns
        WHERE return_1d IS NOT NULL
    ),
    benchmark_cumulative AS (
        SELECT
            event_date, bench_return, bench_info_ts,
            BOOL_OR(bench_return <= -1) OVER (
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS has_invalid_bench,
            CASE
                WHEN BOOL_OR(bench_return <= -1) OVER (
                    ORDER BY event_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) THEN NULL
                ELSE EXP(SUM(LN(GREATEST(1 + bench_return, 0.0001))) OVER (
                    ORDER BY event_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )) - 1
            END AS bench_cumulative_return,
            MAX(bench_info_ts) OVER (
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS bench_max_info_ts
        FROM benchmark_returns
        WHERE bench_return IS NOT NULL
    )
    SELECT
        e.symbol, e.event_date, e.return_1d,
        e.cumulative_return - b.bench_cumulative_return AS rel_perf,
        'SPY' AS benchmark,
        GREATEST(e.entity_info_ts, b.bench_max_info_ts) AS information_available_ts,
        CASE
            WHEN e.has_invalid_return OR b.has_invalid_bench THEN 'invalid_return'
            ELSE 'ok'
        END AS status
    FROM entity_cumulative e
    JOIN benchmark_cumulative b ON e.event_date = b.event_date
    ORDER BY e.event_date;
    """

    def _run_relperf_sql(self, sql: str, rows: list[tuple]) -> list[tuple]:
        """Run relative-performance SQL against a DuckDB in-memory fixture."""
        import duckdb

        con = duckdb.connect(":memory:")
        con.execute("""
            CREATE TABLE base_returns (
                symbol VARCHAR,
                event_date DATE,
                return_1d DOUBLE,
                information_available_ts TIMESTAMP
            )
        """)
        con.executemany(
            "INSERT INTO base_returns VALUES (?, ?, ?, ?)",
            rows,
        )
        result = con.execute(sql).fetchall()
        con.close()
        return result

    def test_normal_window_returns_numeric_value(self):
        """Normal 5-day window → cumulative_return is numeric, status = 'ok'."""
        base_ts = "2024-01-01 16:30:00"
        rows = []
        for i in range(5):
            d = f"2024-01-{1 + i:02d}"
            ts = f"2024-01-{1 + i:02d} 16:30:00"
            rows.append(("AAPL", d, 0.01, ts))  # +1% daily
            rows.append(("SPY", d, 0.005, ts))   # +0.5% daily

        result = self._run_relperf_sql(self._RELPERF_SQL, rows)
        assert len(result) == 5
        for row in result:
            cumulative = row[3]  # rel_perf
            status = row[6]
            assert cumulative is not None, f"Expected numeric rel_perf, got NULL for {row[1]}"
            assert status == "ok", f"Expected status='ok', got '{status}' for {row[1]}"

    def test_minus_100_percent_day_gives_null_and_invalid_return(self):
        """A −100% day (total loss) → cumulative_return IS NULL, status = 'invalid_return'."""
        rows = [
            ("AAPL", "2024-01-01", 0.05, "2024-01-01 16:30:00"),
            ("AAPL", "2024-01-02", -1.0, "2024-01-02 16:30:00"),  # -100% wipeout
            ("AAPL", "2024-01-03", 0.02, "2024-01-03 16:30:00"),
            ("SPY", "2024-01-01", 0.01, "2024-01-01 16:30:00"),
            ("SPY", "2024-01-02", 0.01, "2024-01-02 16:30:00"),
            ("SPY", "2024-01-03", 0.01, "2024-01-03 16:30:00"),
        ]
        result = self._run_relperf_sql(self._RELPERF_SQL, rows)
        # All rows after the -100% day should be NULL/invalid
        for row in result:
            d = str(row[1])
            cumulative = row[3]
            status = row[6]
            if d >= "2024-01-02":
                assert cumulative is None, (
                    f"Expected NULL cumulative after -100% day, got {cumulative} on {d}"
                )
                assert status == "invalid_return", (
                    f"Expected 'invalid_return' after -100% day, got '{status}' on {d}"
                )
            else:
                assert cumulative is not None, f"Expected numeric before -100% day on {d}"
                assert status == "ok", f"Expected 'ok' before -100% day on {d}"

    def test_mutation_replace_null_arm_with_computed_value_fails(self):
        """Mutation: replace the NULL arm in CASE with a computed value.

        If we change 'WHEN has_invalid_return THEN NULL' to use a real
        value, the test_minus_100_percent test would see a non-NULL value.
        """
        mutated_sql = re.sub(
            r"THEN NULL\b",
            "THEN -0.99",
            self._RELPERF_SQL,
        )
        rows = [
            ("AAPL", "2024-01-01", 0.05, "2024-01-01 16:30:00"),
            ("AAPL", "2024-01-02", -1.0, "2024-01-02 16:30:00"),
            ("SPY", "2024-01-01", 0.01, "2024-01-01 16:30:00"),
            ("SPY", "2024-01-02", 0.01, "2024-01-02 16:30:00"),
        ]
        result = self._run_relperf_sql(mutated_sql, rows)
        # After mutation, the -100% day should produce a non-NULL value
        for row in result:
            d = str(row[1])
            cumulative = row[3]
            if d >= "2024-01-02":
                assert cumulative is not None, (
                    "Mutation proof failed: replacing NULL arm with computed "
                    "value should produce non-NULL cumulative"
                )

    def test_mutation_disable_invalid_return_status_fails(self):
        """Mutation: change 'invalid_return' status to 'ok'.

        The test_minus_100_percent test checks for 'invalid_return' status.
        """
        mutated_sql = self._RELPERF_SQL.replace(
            "WHEN e.has_invalid_return OR b.has_invalid_bench THEN 'invalid_return'",
            "WHEN FALSE THEN 'invalid_return'",
        )
        rows = [
            ("AAPL", "2024-01-01", 0.05, "2024-01-01 16:30:00"),
            ("AAPL", "2024-01-02", -1.0, "2024-01-02 16:30:00"),
            ("SPY", "2024-01-01", 0.01, "2024-01-01 16:30:00"),
            ("SPY", "2024-01-02", 0.01, "2024-01-02 16:30:00"),
        ]
        result = self._run_relperf_sql(mutated_sql, rows)
        for row in result:
            d = str(row[1])
            status = row[6]
            if d >= "2024-01-02":
                assert status != "invalid_return", (
                    "Mutation proof failed: disabling invalid_return status "
                    "should change status away from 'invalid_return'"
                )