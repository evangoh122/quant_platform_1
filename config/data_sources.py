"""config/data_sources.py — the controlled ``data_source`` vocabulary.

Owner decision 2026-10-22 (``.agents/requests/RULE-data-source-column.md``):
every table, view, config row, snapshot record and knowledge-graph row this
repository produces carries a non-null ``data_source`` holding exactly one code
from :data:`DATA_SOURCES`.

The vocabulary is defined once here and imported everywhere; do not copy the
list into another module or into a test (a test asserts this exact set and the
loader validates against it).
"""
from __future__ import annotations

DATA_SOURCES: frozenset[str] = frozenset(
    {
        # Massive (Polygon) S3 flat files / REST: OHLCV, options, splits, dividends.
        "massive",
        # SEC EDGAR filings and the submissions API (data.sec.gov/submissions).
        "sec_edgar",
        # SEC XBRL Company-Facts API.
        "sec_companyfacts",
        # Hyperliquid info API (HIP-3 perps, funding, candles).
        "hyperliquid",
        # Binance USD-M futures (data.binance.vision archives / API).
        "binance_um",
        # Hand-maintained repository config (e.g. a universe YAML).
        "config",
        # Computed in this project from other rows; record the inputs' sources
        # in lineage/docs when a row mixes sources.
        "derived",
    }
)


def validate_data_source(value: object) -> str:
    """Return ``value`` when it is one known provider code, else raise.

    Fail-closed by design: a missing (``None``), empty, non-string or unknown
    value is a ``ValueError`` so a typo cannot silently create an
    unprovenanced row.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"data_source must be a string, got {type(value).__name__} "
            f"{value!r}; expected one of {sorted(DATA_SOURCES)}"
        )
    if not value.strip():
        raise ValueError(
            f"data_source must not be empty; expected one of "
            f"{sorted(DATA_SOURCES)}"
        )
    if value not in DATA_SOURCES:
        raise ValueError(
            f"unknown data_source {value!r}; expected one of "
            f"{sorted(DATA_SOURCES)}"
        )
    return value


if __name__ == "__main__":
    print(f"data sources ({len(DATA_SOURCES)}): {', '.join(sorted(DATA_SOURCES))}")
