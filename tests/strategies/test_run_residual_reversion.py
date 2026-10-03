"""Tests for run_residual_reversion helpers."""

import pytest

from strategies.run_residual_reversion import parse_round_from_output


class TestParseRoundFromOutput:
    def test_parses_r1(self):
        assert parse_round_from_output("strategies/results/residual_reversion_r1.md") == 1

    def test_parses_r4(self):
        assert parse_round_from_output("strategies/results/residual_reversion_r4.md") == 4

    def test_parses_r12(self):
        assert parse_round_from_output("residual_reversion_r12.md") == 12

    def test_raises_on_no_match(self):
        with pytest.raises(ValueError, match="cannot derive round"):
            parse_round_from_output("strategies/results/residual_reversion.md")

    def test_raises_on_wrong_suffix(self):
        with pytest.raises(ValueError, match="cannot derive round"):
            parse_round_from_output("strategies/results/residual_reversion_r3.txt")