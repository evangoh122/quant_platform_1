"""Injection-regression tests — pure, no network, no DB, no pyspark.

A symbol shaped like ``'; DROP TABLE users; --`` must be rejected before it
reaches any SQL or Spark expression.
"""
import pytest

from agent.guardrails import normalize_symbol
from agent.tools_retrieval import (
    get_cot_positioning,
    get_options_features,
    search_sec_filings,
)

_BAD_SYMBOLS = [
    "'; DROP TABLE users; --",
    "AAPL' OR '1'='1",
    "x; DELETE FROM orders",
    "AAPL --",
    "AAPL; SELECT pg_sleep(10)",
    "' OR 1=1 --",
    "AAPL\nDROP TABLE orders",
    "AAPL\"; DELETE FROM users",
]


@pytest.mark.parametrize("bad", _BAD_SYMBOLS)
def test_injection_rejected_by_normalizer(bad):
    with pytest.raises(ValueError):
        normalize_symbol(bad)


@pytest.mark.parametrize("bad", _BAD_SYMBOLS)
def test_injection_rejected_by_retrieval_tools(bad):
    # Each tool normalises the symbol first; the ValueError fires before any
    # Spark/DB access, so these run without pyspark or network.
    with pytest.raises(ValueError):
        search_sec_filings(bad)
    with pytest.raises(ValueError):
        get_options_features(bad)
    with pytest.raises(ValueError):
        get_cot_positioning(bad)


def test_normal_symbol_accepted():
    assert normalize_symbol("aapl") == "AAPL"
    assert normalize_symbol("BRK.B") == "BRK.B"
