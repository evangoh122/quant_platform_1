# Databricks notebook source
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # 01 — Ingest Market Data (Stock OHLCV + Options) — Polygon Only
# MAGIC
# MAGIC **Writes to:**
# MAGIC - `bootcamp_students.evangoh_capstone.bronze_ohlcv` — equity daily + minute bars
# MAGIC - `bootcamp_students.evangoh_capstone.bronze_options_quotes` — options quote snapshots **(Volume source: target ≥5M rows)**
# MAGIC - `bootcamp_students.evangoh_capstone.bronze_options_trades` — options trade bars
# MAGIC
# MAGIC **Source:** [Polygon.io](https://polygon.io) REST API (API key required in Databricks secrets `capstone/polygon_api_key`)
# MAGIC
# MAGIC **Run order:**
# MAGIC 1. `pip install` cell
# MAGIC 2. Config cell (set UNIVERSE, date ranges, validate API key)
# MAGIC 3. Stage A: Polygon **daily** OHLCV bars (2-year lookback, adjusted)
# MAGIC 4. Stage B: Polygon **minute** OHLCV bars (30-day lookback, with VWAP + transactions)
# MAGIC 5. Stage C: Polygon **options chain** snapshots (all listed contracts → quotes + trades)
# MAGIC 6. Verification / row counts
# MAGIC
# MAGIC **Polygon plan notes:**
# MAGIC - Free: 2yr history, 5 API calls/min. Starter: unlimited history, 100 calls/min.
# MAGIC - Rate limiting is built in (configurable `RATE_DELAY` in config).

# COMMAND ----------

# DBTITLE 1,Install packages
# MAGIC %pip install -q polygon-api-client>=1.12.0
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Config: Universe, date range, Polygon API key
import os, sys, time
from datetime import datetime, date, timedelta, timezone
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
import pyspark.sql.types as T
from polygon import RESTClient

spark = SparkSession.builder.getOrCreate()

# ── Unity Catalog target ──────────────────────────────────────────────────────
CATALOG = "bootcamp_students"
SCHEMA  = "evangoh_capstone"

def fqn(t): return f"{CATALOG}.{SCHEMA}.{t}"
def _now(): return datetime.now(timezone.utc)

# ── MVP universe (20 highly liquid US equities + ETFs) ────────────────────────
UNIVERSE = [
    # Mega-cap tech (Mag 7)
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA",
    # Semis & AI
    "AMD", "AVGO", "QCOM", "INTC", "MU",
    # Broad market ETFs
    "SPY", "QQQ", "IWM",
    # Sectors
    "XLK", "XLF", "XLE",
    # Volatility proxy
    "VIXY",
    # Financials
    "JPM",
]

# ── Date range ────────────────────────────────────────────────────────────────
DAILY_START  = (date.today() - timedelta(days=730)).isoformat()   # 2 years of daily bars
MINUTE_START = (date.today() - timedelta(days=30)).isoformat()    # 30 days of minute bars
END_DATE     = date.today().isoformat()

# ── Rate limiting ────────────────────────────────────────────────────────────
RATE_DELAY = 12.5   # seconds between API calls (free tier: 5 req/min)
BATCH_SIZE = 10_000 # rows per Delta write flush

# ── Polygon API key (REQUIRED — no fallback) ───────────────────────────────
try:
    POLYGON_API_KEY = dbutils.secrets.get("capstone", "polygon_api_key")
    print("✅ Polygon API key loaded from Databricks secrets (capstone/polygon_api_key)")
except Exception:
    POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
    if POLYGON_API_KEY:
        print("✅ Polygon API key loaded from environment variable")
    else:
        raise RuntimeError(
            "Polygon API key is REQUIRED. Set it via one of:\n"
            "  1. databricks secrets put-secret capstone polygon_api_key\n"
            "  2. export POLYGON_API_KEY=<your_key>\n"
            "Get a free key at https://polygon.io/dashboard/signup"
        )

client = RESTClient(POLYGON_API_KEY)

print(f"[CONFIG] Universe: {len(UNIVERSE)} symbols")
print(f"[CONFIG] Daily bars:  {DAILY_START} → {END_DATE}")
print(f"[CONFIG] Minute bars: {MINUTE_START} → {END_DATE}")
print(f"[CONFIG] Rate limit:  {RATE_DELAY}s between calls ({60/RATE_DELAY:.0f} req/min)")
print(f"[CONFIG] Source: Polygon.io (all stages)")

# COMMAND ----------

# DBTITLE 1,Stage A: Polygon — daily OHLCV bars (2yr lookback)
def _ms_to_dt(ms):
    """Convert Polygon millisecond epoch to timezone-aware datetime."""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

def _flush_ohlcv(rows):
    """Flush a batch of OHLCV rows to Delta."""
    if not rows:
        return 0
    sdf = spark.createDataFrame(rows)
    sdf.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(fqn("bronze_ohlcv"))
    return len(rows)

def ingest_polygon_bars(symbols: list, start: str, end: str, timespan: str = "day") -> int:
    """
    Fetch OHLCV bars from Polygon REST API.
    
    Polygon aggregates endpoint: /v2/aggs/ticker/{ticker}/range/{mult}/{timespan}/{from}/{to}
    Returns: open, high, low, close, volume, vwap, transactions, timestamp
    
    Args:
        symbols:  list of tickers
        start:    ISO date string (YYYY-MM-DD)
        end:      ISO date string
        timespan: 'day' or 'minute'
    """
    all_rows = []
    ingest_ts = _now()
    total = 0

    for idx, symbol in enumerate(symbols, 1):
        try:
            aggs = client.get_aggs(
                ticker=symbol,
                multiplier=1,
                timespan=timespan,
                from_=start,
                to=end,
                adjusted=True,
                limit=50000,
            )
            row_count = 0
            for a in aggs:
                all_rows.append({
                    "symbol":       symbol,
                    "event_ts":     _ms_to_dt(getattr(a, "timestamp", None)),
                    "timespan":     timespan,
                    "open":         float(getattr(a, "open", 0))         if getattr(a, "open", None) is not None else None,
                    "high":         float(getattr(a, "high", 0))         if getattr(a, "high", None) is not None else None,
                    "low":          float(getattr(a, "low", 0))          if getattr(a, "low", None) is not None else None,
                    "close":        float(getattr(a, "close", 0))        if getattr(a, "close", None) is not None else None,
                    "volume":       float(getattr(a, "volume", 0))       if getattr(a, "volume", None) is not None else None,
                    "vwap":         float(getattr(a, "vwap", 0))         if getattr(a, "vwap", None) is not None else None,
                    "transactions": int(getattr(a, "transactions", 0))   if getattr(a, "transactions", None) is not None else None,
                    "source":       "polygon",
                    "ingest_ts":    ingest_ts,
                    "raw_payload":  None,
                })
                row_count += 1

                if len(all_rows) >= BATCH_SIZE:
                    total += _flush_ohlcv(all_rows)
                    all_rows.clear()

            print(f"  [{idx}/{len(symbols)}] {symbol}: {row_count:,} {timespan} bars")
        except Exception as e:
            print(f"  [ERROR] {symbol}: {e}")
        time.sleep(RATE_DELAY)

    total += _flush_ohlcv(all_rows)
    return total


print(f"=== Stage A: Polygon daily bars ({DAILY_START} → {END_DATE}) ===")
total_a = ingest_polygon_bars(UNIVERSE, DAILY_START, END_DATE, timespan="day")
print(f"\n[DONE] Stage A: {total_a:,} daily bar rows written to bronze_ohlcv")

# COMMAND ----------

# DBTITLE 1,Stage B: Polygon — minute OHLCV bars (30-day lookback)
# Re-uses ingest_polygon_bars() from Stage A with timespan="minute"
# 30 days x 390 min/day x 20 symbols = ~234,000 minute bars minimum

print(f"=== Stage B: Polygon minute bars ({MINUTE_START} → {END_DATE}) ===")
print(f"  Expected: ~{20 * 30 * 390:,} minute bars (20 symbols x 30 days x 390 min/session)")
total_b = ingest_polygon_bars(UNIVERSE, MINUTE_START, END_DATE, timespan="minute")
print(f"\n[DONE] Stage B: {total_b:,} minute bar rows written to bronze_ohlcv")

# COMMAND ----------

# DBTITLE 1,Stage C: Polygon — options chain snapshots (quotes + trades)
def ingest_polygon_options(symbols: list) -> tuple:
    """
    Fetch full options chain snapshots via Polygon REST API.
    
    Uses: client.list_snapshot_options_chain(underlying_asset)
    Returns ALL listed contracts for each underlying — all expiries, all strikes.
    
    SPY alone has ~5,000+ active contracts.
    20 symbols x ~2,000 avg contracts = ~40,000+ rows per run.
    Scheduled daily for 125 days reaches the ≥5M row Volume threshold.
    
    Writes to both:
      - bronze_options_quotes (bid/ask/mid/IV/OI)
      - bronze_options_trades (last trade price + day volume)
    """
    ingest_ts = _now()
    quote_rows = []
    trade_rows = []
    total_q = total_t = 0

    def flush_q(r):
        if not r: return 0
        spark.createDataFrame(r).write.format("delta").mode("append") \
            .option("mergeSchema", "true").saveAsTable(fqn("bronze_options_quotes"))
        return len(r)

    def flush_t(r):
        if not r: return 0
        spark.createDataFrame(r).write.format("delta").mode("append") \
            .option("mergeSchema", "true").saveAsTable(fqn("bronze_options_trades"))
        return len(r)

    for idx, symbol in enumerate(symbols, 1):
        try:
            snapshots = client.list_snapshot_options_chain(
                underlying_asset=symbol,
                limit=250,
            )
            sym_q = sym_t = 0
            for snap in snapshots:
                details = getattr(snap, "details", None)
                day     = getattr(snap, "day", None)
                last_q  = getattr(snap, "last_quote", None)
                last_t  = getattr(snap, "last_trade", None)

                opt_sym  = getattr(snap, "ticker", "")
                expiry   = getattr(details, "expiration_date", None) if details else None
                strike   = getattr(details, "strike_price",   None) if details else None
                ctype    = (getattr(details, "contract_type", "") or "") if details else ""
                right    = ctype.upper()[:1] if ctype else None  # "call" -> "C", "put" -> "P"

                bid      = getattr(last_q, "bid",      None) if last_q else None
                ask      = getattr(last_q, "ask",      None) if last_q else None
                bid_sz   = getattr(last_q, "bid_size", None) if last_q else None
                ask_sz   = getattr(last_q, "ask_size", None) if last_q else None
                mid      = (bid + ask) / 2 if bid is not None and ask is not None else None

                iv       = getattr(snap, "implied_volatility", None)
                oi       = getattr(snap, "open_interest",      None)

                last_px  = getattr(last_t, "price",  None) if last_t else None
                volume   = getattr(day,    "volume", None) if day else None
                vwap     = getattr(day,    "vwap",   None) if day else None

                # ── Quote record ────────────────────────────────────────────
                quote_rows.append({
                    "option_symbol":   opt_sym,
                    "underlying":      symbol,
                    "expiry":          str(expiry) if expiry else None,
                    "strike":          float(strike) if strike is not None else None,
                    "right":           right if right in ("C", "P") else None,
                    "participant_ts":  ingest_ts,
                    "bid":             float(bid) if bid is not None else None,
                    "ask":             float(ask) if ask is not None else None,
                    "midpoint":        float(mid) if mid is not None else None,
                    "bid_size":        int(bid_sz) if bid_sz is not None else None,
                    "ask_size":        int(ask_sz) if ask_sz is not None else None,
                    "iv":              float(iv) if iv is not None else None,
                    "open_interest":   float(oi) if oi is not None else None,
                    "source":          "polygon",
                    "ingest_ts":       ingest_ts,
                    "raw_payload":     None,
                })
                sym_q += 1

                # ── Trade record ────────────────────────────────────────────
                if last_px is not None:
                    trade_rows.append({
                        "option_symbol":  opt_sym,
                        "underlying":     symbol,
                        "expiry":         str(expiry) if expiry else None,
                        "strike":         float(strike) if strike is not None else None,
                        "right":          right if right in ("C", "P") else None,
                        "participant_ts": ingest_ts,
                        "open":           float(last_px), "high": float(last_px),
                        "low":            float(last_px), "close": float(last_px),
                        "volume":         float(volume) if volume is not None else None,
                        "vwap":           float(vwap) if vwap is not None else None,
                        "open_interest":  float(oi) if oi is not None else None,
                        "source":         "polygon",
                        "ingest_ts":      ingest_ts,
                        "raw_payload":    None,
                    })
                    sym_t += 1

                if len(quote_rows) >= BATCH_SIZE:
                    total_q += flush_q(quote_rows); quote_rows.clear()
                if len(trade_rows) >= BATCH_SIZE:
                    total_t += flush_t(trade_rows); trade_rows.clear()

            print(f"  [{idx}/{len(symbols)}] {symbol}: {sym_q:,} quotes, {sym_t:,} trades")
        except Exception as e:
            print(f"  [ERROR] {symbol} options: {e}")
        time.sleep(RATE_DELAY)

    total_q += flush_q(quote_rows)
    total_t += flush_t(trade_rows)
    return total_q, total_t


print("=== Stage C: Polygon options chain snapshots ===")
print("  SPY alone has ~5,000+ contracts → Volume threshold target")
total_q, total_t = ingest_polygon_options(UNIVERSE)
print(f"\n[DONE] Stage C: {total_q:,} quote rows, {total_t:,} trade rows")

# COMMAND ----------

# DBTITLE 1,Verification: Row counts + source check
# MAGIC %sql
# MAGIC -- Row counts across all three bronze market tables (all Polygon sourced)
# MAGIC SELECT 'bronze_ohlcv'           AS table_name, COUNT(*) AS total_rows,
# MAGIC        COUNT(DISTINCT symbol)    AS symbols,
# MAGIC        MIN(event_ts)             AS earliest,
# MAGIC        MAX(event_ts)             AS latest,
# MAGIC        COUNT(CASE WHEN timespan='minute' THEN 1 END) AS minute_bars,
# MAGIC        COUNT(CASE WHEN timespan='day'    THEN 1 END) AS daily_bars,
# MAGIC        COLLECT_SET(source)       AS sources
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_ohlcv
# MAGIC
# MAGIC UNION ALL
# MAGIC
# MAGIC SELECT 'bronze_options_quotes'  AS table_name, COUNT(*) AS total_rows,
# MAGIC        COUNT(DISTINCT underlying) AS symbols,
# MAGIC        MIN(participant_ts)         AS earliest,
# MAGIC        MAX(participant_ts)         AS latest,
# MAGIC        NULL AS minute_bars,
# MAGIC        NULL AS daily_bars,
# MAGIC        COLLECT_SET(source)       AS sources
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_options_quotes
# MAGIC
# MAGIC UNION ALL
# MAGIC
# MAGIC SELECT 'bronze_options_trades'  AS table_name, COUNT(*) AS total_rows,
# MAGIC        COUNT(DISTINCT underlying) AS symbols,
# MAGIC        MIN(participant_ts)         AS earliest,
# MAGIC        MAX(participant_ts)         AS latest,
# MAGIC        NULL AS minute_bars,
# MAGIC        NULL AS daily_bars,
# MAGIC        COLLECT_SET(source)       AS sources
# MAGIC FROM bootcamp_students.evangoh_capstone.bronze_options_trades

# COMMAND ----------

# DBTITLE 1,Ingestion summary
# Print final summary
print("=" * 60)
print("MARKET DATA INGESTION COMPLETE (All Polygon)")
print("=" * 60)
print(f"  Stage A (daily bars):       {total_a:>10,} rows")
print(f"  Stage B (minute bars):      {total_b:>10,} rows")
print(f"  Stage C (options quotes):   {total_q:>10,} rows")
print(f"  Stage C (options trades):   {total_t:>10,} rows")
print(f"  " + "-" * 40)
print(f"  TOTAL:                      {total_a + total_b + total_q + total_t:>10,} rows")
print()
print("Target tables:")
print(f"  {fqn('bronze_ohlcv')}")
print(f"  {fqn('bronze_options_quotes')}")
print(f"  {fqn('bronze_options_trades')}")