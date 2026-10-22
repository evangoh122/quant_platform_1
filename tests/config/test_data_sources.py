"""tests/config/test_data_sources.py — the shared ``data_source`` vocabulary.

Owner decision 2026-10-22 (``.agents/requests/RULE-data-source-column.md``):
the vocabulary lives once in ``config/data_sources.py`` and every produced row
uses it. These tests pin the exact set and the fail-closed validator.
"""
from __future__ import annotations

import pytest

from config.data_sources import DATA_SOURCES, validate_data_source

# The owner-approved table from RULE-data-source-column.md. This literal is the
# contract: adding a code to the module alone is a change to that contract.
EXPECTED_CODES = {
    "massive",
    "sec_edgar",
    "sec_companyfacts",
    "hyperliquid",
    "binance_um",
    "config",
    "derived",
}


def test_vocabulary_is_exactly_the_owner_approved_set():
    assert isinstance(DATA_SOURCES, frozenset)
    assert set(DATA_SOURCES) == EXPECTED_CODES


@pytest.mark.parametrize("code", sorted(EXPECTED_CODES))
def test_accepts_every_known_code(code):
    assert validate_data_source(code) == code


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        None,
        "Massive",  # provider codes are lower-case
        "MASSIVE",
        "polygon",  # vendor alias, not a vocabulary code
        " massive",  # no implicit trimming: the stored value must be canonical
        7,
        ["massive"],
        {"data_source": "massive"},
    ],
)
def test_rejects_empty_unknown_and_non_string_values(bad):
    with pytest.raises(ValueError):
        validate_data_source(bad)


def test_error_message_lists_the_vocabulary():
    with pytest.raises(ValueError) as excinfo:
        validate_data_source("polygon")
    message = str(excinfo.value)
    assert "polygon" in message
    for code in EXPECTED_CODES:
        assert code in message
