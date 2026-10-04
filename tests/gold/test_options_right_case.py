"""
tests/gold/test_options_right_case.py
Case-insensitive `right` column tests for gold/02_gold_options_features.sql.

Verifies:
  1. Gold SQL uses UPPER(right) for every comparison (regex scan).
  2. DuckDB semantic test: day CTE counts all case variants.
  3. Ingestion helper emits uppercase 'PUT'/'CALL'.
  4. Repo-wide: no SQL/py compares option side case-sensitively.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD_SQL = REPO_ROOT / "gold" / "02_gold_options_features.sql"

# Regex: any bare `right = '...'` or `right IN ('...')` NOT wrapped in UPPER/LOWER.
_BARE_RIGHT_RE = re.compile(
    r"""(?<!UPPER\()(?<!LOWER\()(?<!upper\()(?<!lower\()"""
    r"""right\s*(=|IN\s*\()\s*'[^']*'""",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 1. Gold SQL: every `right` comparison must be case-insensitive
# ---------------------------------------------------------------------------

def test_gold_sql_right_comparisons_are_case_insensitive():
    """Parse gold/02 and fail if any comparison on `right` is not wrapped in
    UPPER() or LOWER()."""
    sql = GOLD_SQL.read_text()
    # Strip comments to avoid false positives on commented-out code.
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    clean = "\n".join(lines)
    matches = _BARE_RIGHT_RE.findall(clean)
    assert matches == [], (
        f"Found {len(matches)} bare `right` comparison(s) not wrapped in "
        f"UPPER/LOWER in {GOLD_SQL.name}: {matches}"
    )


# ---------------------------------------------------------------------------
# 2. DuckDB semantic test: day CTE counts all case variants
# ---------------------------------------------------------------------------

_DAY_CTE = """
WITH day AS (
    SELECT
      underlying AS symbol,
      event_date AS d,
      SUM(CASE WHEN UPPER("right") = 'PUT'  THEN volume ELSE 0 END) AS put_volume,
      SUM(CASE WHEN UPPER("right") = 'CALL' THEN volume ELSE 0 END) AS call_volume,
      SUM(volume) AS total_volume
    FROM bronze_options_day
    WHERE underlying IS NOT NULL
      AND event_date IS NOT NULL
    GROUP BY underlying, event_date
)
SELECT symbol, d, put_volume, call_volume, total_volume
FROM day
ORDER BY symbol, d
"""


@pytest.fixture
def duckdb_conn():
    """In-memory DuckDB connection."""
    duckdb = pytest.importorskip("duckdb")
    return duckdb.connect(":memory:")


@pytest.fixture
def day_fixture(duckdb_conn):
    """Create bronze_options_day table with mixed-case right values."""
    duckdb_conn.execute("""
        CREATE TABLE bronze_options_day (
            underlying STRING,
            event_date DATE,
            "right"    STRING,
            volume     BIGINT
        )
    """)
    duckdb_conn.execute("""
        INSERT INTO bronze_options_day VALUES
            ('AAPL', '2026-09-01', 'PUT',  100),
            ('AAPL', '2026-09-01', 'CALL', 200),
            ('AAPL', '2026-09-02', 'put',  150),
            ('AAPL', '2026-09-02', 'call', 250),
            ('SPY',  '2026-09-01', 'PUT',  300),
            ('SPY',  '2026-09-01', 'put',  100),
            ('SPY',  '2026-09-01', 'CALL', 400),
            ('SPY',  '2026-09-01', 'call',  50)
    """)
    return duckdb_conn


def test_day_cte_counts_all_case_variants(duckdb_conn, day_fixture):
    """The day CTE must count all case variants (PUT/put/CALL/call)."""
    result = duckdb_conn.execute(_DAY_CTE).fetchall()
    # AAPL 2026-09-01: put_volume=100, call_volume=200, total=300
    # AAPL 2026-09-02: put_volume=150, call_volume=250, total=400
    # SPY  2026-09-01: put_volume=400, call_volume=450, total=850
    rows = {r[0] + "|" + str(r[1]): r for r in result}
    assert rows["AAPL|2026-09-01"][2] == 100   # put_volume
    assert rows["AAPL|2026-09-01"][3] == 200   # call_volume
    assert rows["AAPL|2026-09-02"][2] == 150   # put_volume (lowercase)
    assert rows["AAPL|2026-09-02"][3] == 250   # call_volume (lowercase)
    assert rows["SPY|2026-09-01"][2] == 400    # put_volume (PUT+put)
    assert rows["SPY|2026-09-01"][3] == 450    # call_volume (CALL+call)


def test_mutation_proof_revert_upper_fails(duckdb_conn, day_fixture):
    """Mutation proof: reverting one UPPER() to bare `right =` makes the test
    fail because lowercase rows are missed."""
    # Mutated SQL: bare `right = 'PUT'` (no UPPER) — lowercase 'put' rows ignored.
    mutated_sql = """
    WITH day AS (
        SELECT
          underlying AS symbol,
          event_date AS d,
          SUM(CASE WHEN "right" = 'PUT'  THEN volume ELSE 0 END) AS put_volume,
          SUM(CASE WHEN UPPER("right") = 'CALL' THEN volume ELSE 0 END) AS call_volume,
          SUM(volume) AS total_volume
        FROM bronze_options_day
        WHERE underlying IS NOT NULL
          AND event_date IS NOT NULL
        GROUP BY underlying, event_date
    )
    SELECT symbol, d, put_volume, call_volume, total_volume
    FROM day
    ORDER BY symbol, d
    """
    result = duckdb_conn.execute(mutated_sql).fetchall()
    rows = {r[0] + "|" + str(r[1]): r for r in result}
    # SPY 2026-09-01: put_volume should be 300 (PUT only) + 100 (put) = 400,
    # but mutated SQL misses the 100 'put' rows → only 300.
    assert rows["SPY|2026-09-01"][2] == 300, (
        "Mutation proof failed: mutated SQL should miss lowercase 'put' rows"
    )


# ---------------------------------------------------------------------------
# 3. Ingestion test: day-agg row builder emits 'PUT'/'CALL'
# ---------------------------------------------------------------------------

def test_parse_opra_symbol_emits_uppercase():
    """parse_opra_symbol must return uppercase 'PUT'/'CALL'."""
    from notebooks import refresh_bronze_options as m
    _, _, right_call, _ = m.parse_opra_symbol("O:AAPL250117C00200000")
    _, _, right_put, _ = m.parse_opra_symbol("O:SPY251219P00430000")
    assert right_call == "CALL"
    assert right_put == "PUT"


def test_right_from_contract_type_emits_uppercase():
    """_right_from_contract_type must return uppercase 'CALL'/'PUT'."""
    from notebooks import refresh_bronze_options as m
    assert m._right_from_contract_type("call") == "CALL"
    assert m._right_from_contract_type("CALL") == "CALL"
    assert m._right_from_contract_type("put") == "PUT"
    assert m._right_from_contract_type("P") == "PUT"
    assert m._right_from_contract_type("weird") is None
    assert m._right_from_contract_type(None) is None


def test_shape_quote_row_right_uppercase():
    """shape_quote_row must emit uppercase 'CALL'/'PUT'."""
    from unittest.mock import MagicMock
    from notebooks import refresh_bronze_options as m
    from datetime import datetime, timezone
    snap = MagicMock()
    snap.details = MagicMock()
    snap.details.ticker = "O:SPY261218C00600000"
    snap.details.expiration_date = "2026-12-18"
    snap.details.strike_price = 600.0
    snap.details.contract_type = "call"
    snap.last_quote = MagicMock()
    snap.last_quote.bid = 10.0
    snap.last_quote.ask = 10.5
    snap.last_quote.bid_size = 12
    snap.last_quote.ask_size = 34
    snap.last_quote.midpoint = None
    snap.last_quote.sip_timestamp = None
    snap.last_quote.participant_timestamp = None
    snap.greeks = MagicMock()
    snap.greeks.delta = 0.6
    snap.greeks.gamma = 0.01
    snap.greeks.theta = -0.2
    snap.greeks.vega = 0.3
    snap.last_trade = MagicMock()
    snap.last_trade.price = 10.25
    snap.day = MagicMock()
    snap.day.volume = 500
    snap.open_interest = 1234
    snap.implied_volatility = 0.35

    snap_ts = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    row = m.shape_quote_row(snap, "SPY", snap_ts)
    assert row["right"] == "CALL"


# ---------------------------------------------------------------------------
# 4. Repo-wide: no SQL/py compares option side case-sensitively
# ---------------------------------------------------------------------------

_CASE_SENSITIVE_RIGHT_RE = re.compile(
    r"""(?<!UPPER\()(?<!LOWER\()(?<!upper\()(?<!lower\()"""
    r"""right\s*(=|IN\s*\()\s*'(?:put|call|PUT|CALL)'""",
    re.IGNORECASE,
)


def test_repo_wide_no_case_sensitive_right_comparisons():
    """Scan silver/, gold/, pipelines/ for bare `right = 'put'/'call'/'PUT'/'CALL'
    comparisons not wrapped in UPPER/LOWER."""
    dirs = ["silver", "gold", "pipelines"]
    violations = []
    for d in dirs:
        dir_path = REPO_ROOT / d
        if not dir_path.exists():
            continue
        for sql_file in dir_path.rglob("*.sql"):
            text = sql_file.read_text()
            lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
            clean = "\n".join(lines)
            for match in _CASE_SENSITIVE_RIGHT_RE.finditer(clean):
                violations.append(f"{sql_file.relative_to(REPO_ROOT)}:{match.start()}: {match.group()}")
    assert violations == [], (
        f"Found {len(violations)} case-sensitive `right` comparison(s):\n"
        + "\n".join(violations)
    )