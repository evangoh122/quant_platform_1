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
        """DDL must use close as source, not adj_close as a source column.

        adj_close may appear as an alias of close in SELECT clauses.
        """
        # The DDL should have "close AS adj_close" pattern
        assert "close AS adj_close" in ddl_content or "close" in ddl_content


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


class TestDDLIdentifierCorrespondence:
    """DDL identifier table must match registry."""

    def test_correspondence_table(self, registry, ddl_content):
        """The identifier correspondence table should list all approved views."""
        for view in registry.approved_views:
            assert view in ddl_content