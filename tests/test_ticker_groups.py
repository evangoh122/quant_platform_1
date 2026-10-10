"""
tests/test_ticker_groups.py
Verify POLYGON_GROUPS filtering works for semiconductors.
"""


class TestGroupFiltering:
    """Verify POLYGON_GROUPS filtering works for semiconductors."""

    def test_get_tickers_by_groups(self):
        """Verify get_tickers_by_groups returns correct tickers."""
        from config.tickers import get_tickers_by_groups

        semis = get_tickers_by_groups(["semiconductors"])
        assert len(semis) > 0
        symbols = [t["symbol"] for t in semis]
        assert "NVDA" in symbols
        assert "AMD" in symbols
        assert "INTC" in symbols

    def test_combined_semis_groups(self):
        """Verify combining both semiconductor groups."""
        from config.tickers import get_tickers_by_groups

        all_semis = get_tickers_by_groups([
            "semiconductors",
            "semiconductor_equipment_and_materials"
        ])
        symbols = [t["symbol"] for t in all_semis]
        # Should have both chip designers and equipment makers
        assert "NVDA" in symbols  # semiconductors
        assert "ASML" in symbols  # semiconductor_equipment_and_materials
        assert "AMAT" in symbols  # semiconductor_equipment_and_materials
        # No duplicates
        assert len(all_semis) == len(set(symbols))
