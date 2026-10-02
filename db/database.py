"""
db/database.py
DuckDB-backed local storage for tests and standalone ETL runs.
The Spark/Delta production path lives in delta_adapter.py.
"""
import os
import duckdb

DB_PATH = os.environ.get("DB_PATH", "ibkr_data.duckdb")

_TABLE_DDL = [
    # ── Bronze: Polygon ──────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS polygon_bars (
        ticker       TEXT NOT NULL,
        ts           TEXT NOT NULL,
        timespan     TEXT NOT NULL,
        "open"       REAL,
        high         REAL,
        low          REAL,
        "close"      REAL,
        volume       REAL,
        vwap         REAL,
        transactions INTEGER,
        created_at   TIMESTAMP DEFAULT now(),
        UNIQUE(ticker, ts, timespan)
    )""",
    """CREATE TABLE IF NOT EXISTS polygon_trades (
        ticker      TEXT NOT NULL,
        ts          TEXT NOT NULL,
        price       REAL,
        size        REAL,
        conditions  TEXT,
        exchange    INTEGER,
        tape        TEXT,
        created_at  TIMESTAMP DEFAULT now(),
        UNIQUE(ticker, ts, exchange)
    )""",
    """CREATE TABLE IF NOT EXISTS polygon_snapshots (
        ticker     TEXT,
        ts         TIMESTAMP,
        bid        DOUBLE,
        ask        DOUBLE,
        last       DOUBLE,
        prev_close DOUBLE,
        day_volume BIGINT
    )""",
    """CREATE TABLE IF NOT EXISTS polygon_option_snapshots (
        underlying    TEXT,
        expiry        TEXT,
        strike        DOUBLE,
        "right"       TEXT,
        ts            TIMESTAMP,
        day_open      DOUBLE,
        day_close     DOUBLE,
        day_volume    BIGINT,
        open_interest DOUBLE,
        implied_vol   DOUBLE,
        delta         DOUBLE,
        gamma         DOUBLE,
        theta         DOUBLE,
        vega          DOUBLE
    )""",
    """CREATE TABLE IF NOT EXISTS polygon_tickers (
        ticker           TEXT,
        name             TEXT,
        market           TEXT,
        primary_exchange TEXT,
        "type"           TEXT,
        active           INTEGER,
        currency         TEXT,
        description      TEXT,
        updated_at       TIMESTAMP,
        UNIQUE(ticker)
    )""",
    """CREATE TABLE IF NOT EXISTS polygon_option_bars (
        option_ticker TEXT NOT NULL,
        underlying    TEXT NOT NULL,
        expiry        TEXT,
        strike        REAL,
        "right"       TEXT,
        ts            TEXT NOT NULL,
        timespan      TEXT NOT NULL,
        "open"        REAL,
        high          REAL,
        low           REAL,
        "close"       REAL,
        volume        REAL,
        vwap          REAL,
        transactions  INTEGER,
        created_at    TIMESTAMP DEFAULT now(),
        UNIQUE(option_ticker, ts, timespan)
    )""",
    # ── Bronze: IBKR ─────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS stock_quotes (
        ticker  TEXT,
        ts      TIMESTAMP,
        bid     DOUBLE,
        ask     DOUBLE,
        last    DOUBLE,
        close   DOUBLE,
        volume  BIGINT,
        "open"  DOUBLE,
        high    DOUBLE,
        low     DOUBLE,
        vwap    DOUBLE
    )""",
    """CREATE TABLE IF NOT EXISTS option_quotes (
        ticker        TEXT,
        expiry        TEXT,
        strike        DOUBLE,
        "right"       TEXT,
        ts            TIMESTAMP,
        bid           DOUBLE,
        ask           DOUBLE,
        last          DOUBLE,
        volume        BIGINT,
        open_interest DOUBLE,
        implied_vol   DOUBLE,
        delta         DOUBLE,
        gamma         DOUBLE,
        theta         DOUBLE,
        vega          DOUBLE,
        und_price     DOUBLE,
        pv_dividend   DOUBLE
    )""",
    """CREATE TABLE IF NOT EXISTS option_chains (
        ticker  TEXT,
        expiry  TEXT,
        strike  DOUBLE,
        "right" TEXT,
        UNIQUE(ticker, expiry, strike, "right")
    )""",
    # ── Bronze: yFinance ─────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS staging_yf_bars (
        ticker     TEXT,
        ts         TEXT,
        "open"     DOUBLE,
        high       DOUBLE,
        low        DOUBLE,
        "close"    DOUBLE,
        adj_close  DOUBLE,
        volume     DOUBLE,
        dividends  DOUBLE,
        splits     DOUBLE,
        UNIQUE(ticker, ts)
    )""",
    """CREATE TABLE IF NOT EXISTS staging_yf_indices (
        symbol    TEXT,
        ts        TEXT,
        "open"    DOUBLE,
        high      DOUBLE,
        low       DOUBLE,
        "close"   DOUBLE,
        adj_close DOUBLE,
        volume    DOUBLE,
        UNIQUE(symbol, ts)
    )""",
    """CREATE TABLE IF NOT EXISTS staging_yf_index_stats (
        symbol               TEXT,
        ts                   TEXT,
        ret_1d               DOUBLE,
        ret_21d              DOUBLE,
        ret_252d             DOUBLE,
        vol_21d              DOUBLE,
        vol_63d              DOUBLE,
        vol_252d             DOUBLE,
        drawdown             DOUBLE,
        max_drawdown_to_date DOUBLE,
        sharpe_252d          DOUBLE,
        skew_252d            DOUBLE,
        kurt_252d            DOUBLE,
        mean_252d            DOUBLE,
        sigma_252d           DOUBLE,
        band_plus_1          DOUBLE,
        band_minus_1         DOUBLE,
        band_plus_2          DOUBLE,
        band_minus_2         DOUBLE,
        band_plus_3          DOUBLE,
        band_minus_3         DOUBLE,
        band_plus_4          DOUBLE,
        band_minus_4         DOUBLE
    )""",
    # ── Bronze: EDGAR ────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS edgar_filings (
        ticker            TEXT,
        cik               TEXT,
        form_type         TEXT,
        filed_date        TEXT,
        accession_number  TEXT,
        primary_doc       TEXT,
        UNIQUE(ticker, accession_number)
    )""",
    """CREATE TABLE IF NOT EXISTS edgar_facts (
        ticker            TEXT,
        cik               TEXT,
        taxonomy          TEXT,
        concept           TEXT,
        label             TEXT,
        unit              TEXT,
        value             DOUBLE,
        period_start      TEXT,
        period_end        TEXT,
        form_type         TEXT,
        filed_date        TEXT,
        accession_number  TEXT,
        UNIQUE(ticker, accession_number, concept, period_end)
    )""",
    """CREATE TABLE IF NOT EXISTS edgar_13f (
        filer_cik               TEXT,
        filer_name              TEXT,
        ticker                  TEXT,
        period_of_report        TEXT,
        filed_date              TEXT,
        accession_number        TEXT,
        shares                  BIGINT,
        value                   BIGINT,
        investment_discretion   TEXT,
        put_call                TEXT,
        UNIQUE(filer_cik, ticker, period_of_report, accession_number)
    )""",
    # ── Bronze: COT ──────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS cot_reports (
        market_name     TEXT,
        ticker          TEXT,
        report_date     TEXT,
        noncomm_long    INTEGER,
        noncomm_short   INTEGER,
        comm_long       INTEGER,
        comm_short      INTEGER,
        total_long      INTEGER,
        total_short     INTEGER,
        noncomm_spreads INTEGER,
        open_interest   INTEGER,
        UNIQUE(market_name, report_date)
    )""",
]


def init_db(path: str | None = None):
    """Create all tables in the DuckDB file at *path* (defaults to DB_PATH)."""
    db = path or DB_PATH
    conn = duckdb.connect(db)
    for ddl in _TABLE_DDL:
        conn.execute(ddl)
    conn.close()


def get_connection(path: str | None = None):
    """Open and return a DuckDB connection (caller must close)."""
    db = path or DB_PATH
    return duckdb.connect(db)