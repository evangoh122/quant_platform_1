"""
tests/gold/test_options_right_case.py
Case-insensitive `right` column tests for gold/02_gold_options_features.sql.

Verifies:
  1. Gold SQL uses UPPER(right) for every comparison (regex scan).
  2. DuckDB semantic test: day CTE (extracted from gold/02) counts all case variants.
  3. Ingestion helpers: day path emits uppercase, quotes path emits lowercase.
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
# 2. DuckDB semantic test: day CTE extracted from gold/02
# ---------------------------------------------------------------------------

def _extract_day_cte(sql_text):
    """Extract the `day` CTE from gold/02_gold_options_features.sql.

    Parses between ``WITH day AS (`` and the matching close-paren before the
    next CTE or SELECT.  Three shims are applied (all documented):

    1. The convert_timezone(...)+make_interval(...) availability expression is
       replaced with a literal ``DATE '2026-09-01'`` (DuckDB has no
       convert_timezone).
    2. The ``universe`` subquery
       (``underlying IN (SELECT symbol FROM universe)``) is removed — the
       DuckDB fixture table has no ``universe`` table; the fixture already
       filters to known underlyings.
    3. The fully-qualified Databricks table name
       ``bootcamp_students.evangoh_capstone.bronze_options_day`` is replaced
       with the bare ``bronze_options_day`` (the DuckDB in-memory fixture).
    """
    lines = sql_text.splitlines()
    start_idx = None
    for i, ln in enumerate(lines):
        if "WITH day AS (" in ln:
            start_idx = i
            break
    if start_idx is None:
        raise ValueError("Could not find 'WITH day AS (' in gold SQL")

    depth = 0
    end_idx = None
    for i in range(start_idx, len(lines)):
        for ch in lines[i]:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        if depth == 0 and i > start_idx:
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("Could not find closing paren for day CTE")

    cte_text = "\n".join(lines[start_idx:end_idx + 1])

    # Shim 1: replace convert_timezone(...)+make_interval(...) with a literal.
    avail_block = (
        "convert_timezone('America/New_York', 'UTC',\n"
        "          to_timestamp(concat(cast(event_date AS STRING), ' 16:00:00')))\n"
        "        + make_interval(0, 0, 0, 0, 0, opt_pub_buffer_minutes, 0)"
    )
    cte_text = cte_text.replace(avail_block, "DATE '2026-09-01'")

    # Shim 2: remove the `universe` subquery constraint.  The gold SQL has:
    #   WHERE underlying IN (SELECT symbol FROM universe)
    #     AND underlying IS NOT NULL ...
    # After removal, WHERE attaches directly to `underlying IS NOT NULL`.
    cte_text = re.sub(
        r"underlying\s+IN\s*\(\s*SELECT\s+symbol\s+FROM\s+universe\s*\)\s*\n\s*AND\s+",
        "",
        cte_text,
        flags=re.IGNORECASE,
    )

    # Shim 3: replace fully-qualified Databricks table name with bare name.
    cte_text = cte_text.replace(
        "bootcamp_students.evangoh_capstone.bronze_options_day",
        "bronze_options_day",
    )

    # Shim 4: quote `right` column — it's a reserved keyword in DuckDB
    # (string function RIGHT(str, n)).  Databricks allows it unquoted; DuckDB
    # does not.  Replace bare `right` (column ref, not already quoted or part
    # of a longer identifier) with `"right"`.
    cte_text = re.sub(r'(?<!")\bright\b(?!")', '"right"', cte_text)

    # Strip trailing comma after the closing paren — the gold SQL has
    # `),` between CTEs, but we only extract the day CTE.
    cte_text = cte_text.rstrip()
    if cte_text.endswith(","):
        cte_text = cte_text[:-1]

    return cte_text


# Read and extract once at module load so test failures point at import time.
_GOLD_SQL_TEXT = GOLD_SQL.read_text()
_EXTRACTED_DAY_CTE = _extract_day_cte(_GOLD_SQL_TEXT)

# Append the outer SELECT that the gold SQL wraps around the CTEs.
# The day CTE ends with `)` then `,` — we need just the day part for DuckDB.
_DAY_QUERY = _EXTRACTED_DAY_CTE + """
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
            volume     BIGINT,
            event_ts   TIMESTAMP
        )
    """)
    duckdb_conn.execute("""
        INSERT INTO bronze_options_day VALUES
            ('AAPL', '2026-09-01', 'PUT',  100, TIMESTAMP '2026-09-01 04:00:00'),
            ('AAPL', '2026-09-01', 'CALL', 200, TIMESTAMP '2026-09-01 04:00:00'),
            ('AAPL', '2026-09-02', 'put',  150, TIMESTAMP '2026-09-02 04:00:00'),
            ('AAPL', '2026-09-02', 'call', 250, TIMESTAMP '2026-09-02 04:00:00'),
            ('AAPL', '2026-09-03', 'P',     50, TIMESTAMP '2026-09-03 04:00:00'),
            ('AAPL', '2026-09-03', 'C',     75, TIMESTAMP '2026-09-03 04:00:00'),
            ('SPY',  '2026-09-01', 'PUT',  300, TIMESTAMP '2026-09-01 04:00:00'),
            ('SPY',  '2026-09-01', 'put',  100, TIMESTAMP '2026-09-01 04:00:00'),
            ('SPY',  '2026-09-01', 'CALL', 400, TIMESTAMP '2026-09-01 04:00:00'),
            ('SPY',  '2026-09-01', 'call',  50, TIMESTAMP '2026-09-01 04:00:00'),
            ('SPY',  '2026-09-02', 'P',    120, TIMESTAMP '2026-09-02 04:00:00'),
            ('SPY',  '2026-09-02', 'C',    180, TIMESTAMP '2026-09-02 04:00:00')
    """)
    return duckdb_conn


def test_day_cte_counts_all_case_variants(duckdb_conn, day_fixture):
    """The day CTE must count all case variants (PUT/put/P/CALL/call/C)."""
    result = duckdb_conn.execute(_DAY_QUERY).fetchall()
    # AAPL 2026-09-01: put_volume=100, call_volume=200, total=300
    # AAPL 2026-09-02: put_volume=150, call_volume=250, total=400
    # AAPL 2026-09-03: put_volume=50,  call_volume=75,  total=125  (P/C)
    # SPY  2026-09-01: put_volume=400, call_volume=450, total=850
    # SPY  2026-09-02: put_volume=120, call_volume=180, total=300  (P/C)
    rows = {r[0] + "|" + str(r[1]): r for r in result}
    assert rows["AAPL|2026-09-01"][2] == 100   # put_volume
    assert rows["AAPL|2026-09-01"][3] == 200   # call_volume
    assert rows["AAPL|2026-09-02"][2] == 150   # put_volume (lowercase)
    assert rows["AAPL|2026-09-02"][3] == 250   # call_volume (lowercase)
    assert rows["AAPL|2026-09-03"][2] == 50    # put_volume (P)
    assert rows["AAPL|2026-09-03"][3] == 75    # call_volume (C)
    assert rows["SPY|2026-09-01"][2] == 400    # put_volume (PUT+put)
    assert rows["SPY|2026-09-01"][3] == 450    # call_volume (CALL+call)
    assert rows["SPY|2026-09-02"][2] == 120    # put_volume (P)
    assert rows["SPY|2026-09-02"][3] == 180    # call_volume (C)


def test_extracted_day_cte_contains_upper(duckdb_conn, day_fixture):
    """Mutation proof: the extracted day CTE from gold/02 uses UPPER(right).
    If someone reverts gold/02 to bare `right = 'PUT'`, this test fails because
    lowercase rows are missed."""
    # After shims, `right` is quoted as "right" (DuckDB reserved word).
    assert 'UPPER("right")' in _EXTRACTED_DAY_CTE, (
        "Extracted day CTE does not contain UPPER(\"right\") — gold/02 may have been mutated"
    )


# ---------------------------------------------------------------------------
# 3. Ingestion tests: day path = uppercase, quotes path = lowercase
# ---------------------------------------------------------------------------

def test_parse_opra_symbol_emits_uppercase():
    """parse_opra_symbol (day path) must return uppercase 'PUT'/'CALL'."""
    from notebooks import refresh_bronze_options as m
    _, _, right_call, _ = m.parse_opra_symbol("O:AAPL250117C00200000")
    _, _, right_put, _ = m.parse_opra_symbol("O:SPY251219P00430000")
    assert right_call == "CALL"
    assert right_put == "PUT"


def test_right_from_contract_type_emits_lowercase():
    """_right_from_contract_type (quotes path) must return lowercase 'call'/'put'."""
    from notebooks import refresh_bronze_options as m
    assert m._right_from_contract_type("call") == "call"
    assert m._right_from_contract_type("CALL") == "call"
    assert m._right_from_contract_type("put") == "put"
    assert m._right_from_contract_type("P") == "put"
    assert m._right_from_contract_type("weird") is None
    assert m._right_from_contract_type(None) is None


def test_shape_quote_row_right_lowercase():
    """shape_quote_row (quotes path) must emit lowercase 'call'/'put'."""
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
    assert row["right"] == "call"


def test_quotes_path_lowercase_day_path_uppercase():
    """Quotes path emits lowercase; day path emits uppercase.
    This guards against cross-path regressions."""
    from notebooks import refresh_bronze_options as m
    # Day path: parse_opra_symbol → uppercase
    _, _, day_right, _ = m.parse_opra_symbol("O:AAPL250117C00200000")
    assert day_right == day_right.upper()
    assert day_right == "CALL"

    # Quotes path: _right_from_contract_type → lowercase
    quotes_right = m._right_from_contract_type("call")
    assert quotes_right == quotes_right.lower()
    assert quotes_right == "call"


# ---------------------------------------------------------------------------
# 4. Repo-wide: no SQL/py compares option side case-sensitively
# ---------------------------------------------------------------------------

_CASE_SENSITIVE_RIGHT_RE = re.compile(
    r"""(?<!UPPER\()(?<!LOWER\()(?<!upper\()(?<!lower\()"""
    r"""right\s*(=|IN\s*\()\s*'(?:put|call|PUT|CALL)'""",
    re.IGNORECASE,
)

# Directories to scan for .py files (item 3: widened to include .py)
_PY_SCAN_DIRS = ["pipelines", "ml", "strategies", "api", "analytics_nl", "notebooks"]
_SQL_SCAN_DIRS = ["silver", "gold", "pipelines"]


def test_repo_wide_no_case_sensitive_right_comparisons():
    """Scan silver/, gold/, pipelines/ .sql AND pipelines/, ml/, strategies/,
    api/, analytics_nl/, notebooks/ .py for bare `right = 'put'/'call'/'PUT'/'CALL'
    comparisons not wrapped in UPPER/LOWER.  Excludes tests/ and .agents/."""
    violations = []

    # SQL files
    for d in _SQL_SCAN_DIRS:
        dir_path = REPO_ROOT / d
        if not dir_path.exists():
            continue
        for sql_file in dir_path.rglob("*.sql"):
            if "tests" in sql_file.parts or ".agents" in sql_file.parts:
                continue
            try:
                text = sql_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
            clean = "\n".join(lines)
            for match in _CASE_SENSITIVE_RIGHT_RE.finditer(clean):
                violations.append(f"{sql_file.relative_to(REPO_ROOT)}:{match.start()}: {match.group()}")

    # Python files
    for d in _PY_SCAN_DIRS:
        dir_path = REPO_ROOT / d
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            if "tests" in py_file.parts or ".agents" in py_file.parts:
                continue
            try:
                text = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            # Strip Python comments
            lines = [ln for ln in text.splitlines() if not ln.strip().startswith("#")]
            clean = "\n".join(lines)
            for match in _CASE_SENSITIVE_RIGHT_RE.finditer(clean):
                violations.append(f"{py_file.relative_to(REPO_ROOT)}:{match.start()}: {match.group()}")

    assert violations == [], (
        f"Found {len(violations)} case-sensitive `right` comparison(s):\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# 5. No CRLF in sql/maintenance/*.sql
# ---------------------------------------------------------------------------

def test_no_crlf_in_maintenance_sql():
    """All sql/maintenance/*.sql files must use LF line endings, not CRLF."""
    maint_dir = REPO_ROOT / "sql" / "maintenance"
    if not maint_dir.exists():
        return
    crlf_files = []
    for sql_file in maint_dir.glob("*.sql"):
        raw = sql_file.read_bytes()
        if b"\r\n" in raw:
            crlf_files.append(str(sql_file.relative_to(REPO_ROOT)))
    assert crlf_files == [], (
        f"Found CRLF line endings in: {', '.join(crlf_files)}. "
        "Convert to LF (e.g. `sed -i s/\\r$// file.sql`)."
    )