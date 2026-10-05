"""
tests/gold/test_gold_sec_coverage_sql.py

Semantic tests for gold/07_gold_sec_coverage.sql canonical-ticker logic.

Proves:
- A CIK with GOOG (0 chunks) and GOOGL (831 chunks) → canonical GOOGL;
  both rows report n_chunks = 831 (resolved to GOOGL's corpus).
- A normal single-ticker CIK (NVDA) → unchanged.
- Ticker with zero chunks but same CIK gets alias pointing to the one with data.

Mutation proofs:
- Reverting canonical_per_cik to min(ticker) → FAILS (picks GOOG, which has 0 chunks).
"""
import re
from pathlib import Path

import duckdb
import pytest


# ---------------------------------------------------------------------------
# SQL extraction and Databricks→DuckDB translation shim
# ---------------------------------------------------------------------------

_SQL_PATH = Path(__file__).resolve().parents[2] / "gold" / "07_gold_sec_coverage.sql"


def _extract_sql_text() -> str:
    """Read and return the raw SQL file text."""
    return _SQL_PATH.read_text(encoding="utf-8")


def _build_cte_sql(sql_text: str, cte_name: str) -> str:
    """Extract a single CTE definition by name from the WITH clause.

    Returns the body as a CREATE OR REPLACE VIEW statement.
    """
    # Match optional comment line(s) before the CTE, then the CTE name
    pattern = rf"(?:-- [^\n]*\n)*{cte_name}\s+AS\s*\("
    m = re.search(pattern, sql_text, re.IGNORECASE)
    if not m:
        raise ValueError(f"Could not find CTE '{cte_name}' in SQL file")

    depth = 0
    i = sql_text.index("(", m.end() - 1)
    for j in range(i, len(sql_text)):
        if sql_text[j] == "(":
            depth += 1
        elif sql_text[j] == ")":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    else:
        raise ValueError(f"Unbalanced parentheses in CTE '{cte_name}'")

    body = sql_text[i + 1:end - 1].strip()
    return f"CREATE OR REPLACE VIEW {cte_name} AS {body}"


def _shim_for_duckdb(sql: str) -> str:
    """Translate Databricks-only syntax to DuckDB-compatible SQL."""
    result = sql
    # Strip schema prefixes
    result = result.replace("{catalog}.{schema}.", "")
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def duckdb_conn():
    """Fresh DuckDB connection with fixture tables for SEC coverage."""
    conn = duckdb.connect()

    # gold_tradable_universe: primary universe
    conn.execute("""
        CREATE TABLE gold_tradable_universe (
            symbol VARCHAR
        )
    """)
    conn.execute("""
        INSERT INTO gold_tradable_universe VALUES
        ('GOOG'), ('GOOGL'), ('NVDA')
    """)

    # sec_cik_mapping_log: latest mapping per ticker
    conn.execute("""
        CREATE TABLE sec_cik_mapping_log (
            ticker VARCHAR,
            cik VARCHAR,
            status VARCHAR,
            mapped_ts TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO sec_cik_mapping_log VALUES
        ('GOOG',  '0001652044', 'mapped', '2025-01-01'),
        ('GOOGL', '0001652044', 'mapped', '2025-01-01'),
        ('NVDA',  '0001045810', 'mapped', '2025-01-01')
    """)

    # silver_sec_sections: chunks stored under GOOGL (not GOOG)
    conn.execute("""
        CREATE TABLE silver_sec_sections (
            ticker VARCHAR,
            chunk_id VARCHAR
        )
    """)
    # 831 chunks under GOOGL, 0 under GOOG, 894 under NVDA
    conn.execute("""
        INSERT INTO silver_sec_sections
        SELECT 'GOOGL', 'chunk_' || i::VARCHAR
        FROM generate_series(1, 831) t(i)
    """)
    conn.execute("""
        INSERT INTO silver_sec_sections
        SELECT 'NVDA', 'chunk_' || i::VARCHAR
        FROM generate_series(1, 894) t(i)
    """)

    # bronze_sec_filings_v2 (empty for canonical-ticker test; needed for filing_agg)
    conn.execute("""
        CREATE TABLE bronze_sec_filings_v2 (
            ticker VARCHAR,
            accession_number VARCHAR,
            filing_section VARCHAR,
            chunk_text VARCHAR,
            accepted_ts TIMESTAMP,
            ingest_ts TIMESTAMP
        )
    """)

    yield conn
    conn.close()


@pytest.fixture
def sql_text():
    """Raw SQL from gold/07."""
    return _SQL_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Canonical ticker = max(n_chunks) then alphabetical
# ---------------------------------------------------------------------------

class TestCanonicalTickerSelection:

    def test_google_canonical_is_googl(self, duckdb_conn, sql_text):
        """CIK 0001652044: GOOG (0 chunks) + GOOGL (831 chunks).
        Canonical must be GOOGL (the one with data)."""
        # Extract and build the relevant CTEs
        lm_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "latest_mapping"))
        tcc_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "ticker_chunk_counts"))
        cpc_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "canonical_per_cik"))

        duckdb_conn.execute(lm_sql)
        duckdb_conn.execute(tcc_sql)
        duckdb_conn.execute(cpc_sql)

        results = duckdb_conn.execute(
            "SELECT cik, canonical_ticker FROM canonical_per_cik ORDER BY cik"
        ).fetchall()

        by_cik = {r[0]: r[1] for r in results}
        assert by_cik["0001652044"] == "GOOGL", (
            f"Canonical for CIK 0001652044 should be GOOGL (831 chunks), "
            f"got {by_cik['0001652044']}"
        )

    def test_nvda_canonical_unchanged(self, duckdb_conn, sql_text):
        """Single-ticker CIK: NVDA is its own canonical."""
        lm_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "latest_mapping"))
        tcc_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "ticker_chunk_counts"))
        cpc_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "canonical_per_cik"))

        duckdb_conn.execute(lm_sql)
        duckdb_conn.execute(tcc_sql)
        duckdb_conn.execute(cpc_sql)

        results = duckdb_conn.execute(
            "SELECT cik, canonical_ticker FROM canonical_per_cik ORDER BY cik"
        ).fetchall()

        by_cik = {r[0]: r[1] for r in results}
        assert by_cik["0001045810"] == "NVDA", (
            f"Canonical for CIK 0001045810 should be NVDA, got {by_cik['0001045810']}"
        )

    def test_both_google_rows_resolve_to_googl_chunks(self, duckdb_conn, sql_text):
        """Both GOOG and GOOGL rows in universe_resolved should point to
        canonical_ticker = GOOGL, so both get GOOGL's chunk count (831)."""
        # Build prerequisite CTEs
        univ_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "universe"))
        lm_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "latest_mapping"))
        tcc_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "ticker_chunk_counts"))
        cpc_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "canonical_per_cik"))
        ur_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "universe_resolved"))
        ca_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "chunk_agg"))

        duckdb_conn.execute(univ_sql)
        duckdb_conn.execute(lm_sql)
        duckdb_conn.execute(tcc_sql)
        duckdb_conn.execute(cpc_sql)
        duckdb_conn.execute(ur_sql)
        duckdb_conn.execute(ca_sql)

        results = duckdb_conn.execute("""
            SELECT ur.ticker, ur.canonical_ticker, coalesce(ca.n_chunks, 0) AS n_chunks
            FROM universe_resolved ur
            LEFT JOIN chunk_agg ca ON ur.canonical_ticker = upper(ca.ticker)
            WHERE ur.cik = '0001652044'
            ORDER BY ur.ticker
        """).fetchall()

        by_ticker = {r[0]: (r[1], r[2]) for r in results}

        # Both GOOG and GOOGL should resolve to GOOGL canonical with 831 chunks
        assert by_ticker["GOOG"] == ("GOOGL", 831), (
            f"GOOG should resolve to GOOGL with 831 chunks, got {by_ticker['GOOG']}"
        )
        assert by_ticker["GOOGL"] == ("GOOGL", 831), (
            f"GOOGL should resolve to GOOGL with 831 chunks, got {by_ticker['GOOGL']}"
        )


# ---------------------------------------------------------------------------
# 2. Mutation proof: reverting to min(ticker) breaks the correct canonical
# ---------------------------------------------------------------------------

class TestMutationCanonicalMinTicker:

    def test_mutation_min_ticker_picks_googl_canonical(self, duckdb_conn, sql_text):
        """Mutation: replace canonical_per_cik with min(ticker).
        This picks GOOG (alphabetically first) as canonical, but GOOG has 0 chunks.
        The correct SQL picks GOOGL."""
        lm_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "latest_mapping"))
        tcc_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "ticker_chunk_counts"))

        duckdb_conn.execute(lm_sql)
        duckdb_conn.execute(tcc_sql)

        # Mutated: min(ticker) instead of max(n_chunks) then ticker
        duckdb_conn.execute("""
            CREATE OR REPLACE VIEW canonical_per_cik AS
            SELECT
                cik,
                min(ticker) AS canonical_ticker
            FROM latest_mapping
            GROUP BY cik
        """)

        results = duckdb_conn.execute(
            "SELECT cik, canonical_ticker FROM canonical_per_cik ORDER BY cik"
        ).fetchall()

        by_cik = {r[0]: r[1] for r in results}
        # min(ticker) picks GOOG (alphabetically first) — WRONG
        assert by_cik["0001652044"] == "GOOG", (
            f"Mutation proof: min(ticker) picks GOOG, got {by_cik['0001652044']}"
        )

        # Now verify: with this wrong canonical, GOOG's 0-chunk corpus is used
        duckdb_conn.execute(_shim_for_duckdb(_build_cte_sql(sql_text, "universe")))
        duckdb_conn.execute(_shim_for_duckdb(_build_cte_sql(sql_text, "universe_resolved")))
        ca_sql = _shim_for_duckdb(_build_cte_sql(sql_text, "chunk_agg"))
        duckdb_conn.execute(ca_sql)

        results = duckdb_conn.execute("""
            SELECT ur.ticker, ur.canonical_ticker, coalesce(ca.n_chunks, 0) AS n_chunks
            FROM universe_resolved ur
            LEFT JOIN chunk_agg ca ON ur.canonical_ticker = upper(ca.ticker)
            WHERE ur.cik = '0001652044'
            ORDER BY ur.ticker
        """).fetchall()

        by_ticker = {r[0]: (r[1], r[2]) for r in results}
        # With min(ticker), GOOG is canonical → both rows show 0 chunks (GOOG's corpus)
        assert by_ticker["GOOG"] == ("GOOG", 0), (
            f"Mutation: min(ticker) → GOOG canonical with 0 chunks, got {by_ticker['GOOG']}"
        )
        assert by_ticker["GOOGL"] == ("GOOG", 0), (
            f"Mutation: min(ticker) → GOOGL resolves to GOOG (0 chunks), got {by_ticker['GOOGL']}"
        )