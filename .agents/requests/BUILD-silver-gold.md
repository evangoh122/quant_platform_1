# BUILD-REQUEST: silver-gold

**Round:** 1
**Branch:** `slice/silver-gold` (branched off `refactor/file-structure`, which
created the `silver/` and `gold/` packages you will fill)
**Worktree:** `/home/jianj/code/qp1-sg`
**Rubric requirements covered:** §4.3 Silver layer, §4.4 Gold layer,
§4.5 point-in-time join and no-look-ahead rule, §4.6 data-quality tests.

**This is the project's critical path.** Everything downstream is blocked on it.

---

## The situation, measured

The Bronze layer is large and real. The Silver and Gold layers **do not exist**.

| Layer | Rows (measured 2026-10-02) |
| :-- | --: |
| `bronze_options_day` | 146,117,971 |
| `bronze_ohlcv` | 72,678,354 |
| `bronze_ohlcv_day` | 12,993,270 |
| `bronze_sec_filings_v2` | 72,970 |
| `bronze_options_quotes` | 61,882 |
| `bronze_sec_filings` | 60,893 |
| `bronze_options_trades` | 60,068 |
| `bronze_cftc_fut` / `bronze_cftc_com` | 15,427 / 15,437 |
| `bronze_economic_metrics` | 140,280 |
| **all 6 `silver_*` tables** | **0** |
| **all 6 `gold_*` tables** | **0** |
| **TOTAL** | **232,220,115** |

I verified every `saveAsTable` call in this repo targets a `bronze_*` table.
Nothing writes silver or gold. The twelve tables exist as **empty shells with
schemas already defined**.

Consequences you are fixing: the ML lane had to fall back to synthetic data; the
agent's retrieval tools return nothing; `gold_trading_signals` is empty so there
are no signals; and the whole CDF→analytics chain has no input.

Note `bronze_cot` is **0 rows** — COT data landed in `bronze_cftc_fut` /
`bronze_cftc_com` instead. Build `silver_cot_positions` from the CFTC tables and
say so; do not silently produce an empty table.

---

## Authoritative schemas — read this file first

**`docs/DATA_SCHEMAS.md`** in this branch contains the exact column list, type
and nullability for all nine bronze sources and all twelve silver/gold targets.

**The target tables already exist.** Your transforms must write exactly those
columns with those types. Do not invent, rename, reorder or drop columns, and do
not `CREATE OR REPLACE` a target with a different schema. If a target schema
looks wrong, say so in your verdict — do not unilaterally change it.

Catalog/schema: `bootcamp_students.evangoh_capstone`.

---

## How to actually execute — read this before writing any code

I checked the available compute. **There is no Spark cluster you can use:**

- `databricks clusters list` → 10 clusters exist in this shared workspace,
  **zero belong to this user**.
- `databricks-connect` is **not installed**, and local `pyspark` cannot read
  Unity Catalog Delta tables.
- The **SQL warehouse works** and I verified **write permission** with a
  0-row `INSERT INTO silver_ohlcv ... WHERE 1=0` → `SUCCEEDED`.

**Therefore: write the transforms as SQL and execute them through the SQL
Statement Execution API.** PySpark DataFrame code would be unrunnable here.

```
databricks api post /api/2.0/sql/statements --json '{
  "warehouse_id": "b15d3d6f837ba428",
  "statement": "INSERT INTO ... SELECT ...",
  "wait_timeout": "50s"
}'
```

Notes that will save you time:
- `wait_timeout` caps at 50s. For long statements, poll
  `GET /api/2.0/sql/statements/{statement_id}` until the state leaves `PENDING`/`RUNNING`.
- The warehouse auto-stops; `databricks warehouses start b15d3d6f837ba428`.
- Prefer `INSERT INTO` over `CREATE OR REPLACE TABLE` — the targets already
  exist with fixed schemas and must keep them.
- For idempotency use `MERGE INTO` on the dedup key, or delete-then-insert the
  affected partition inside one statement. Do not rely on re-running a plain
  `INSERT`.
- Column **order** matters for positional `INSERT ... SELECT`; the verified
  `silver_ohlcv` order is exactly as listed in `docs/DATA_SCHEMAS.md`.
- 146M-row sources: work incrementally by date partition rather than one giant
  statement, and report progress.

Keep the SQL in version-controlled `.sql` files under `silver/` and `gold/`,
with a thin Python runner that submits them in dependency order — not SQL
pasted inline in throwaway shell commands.

---

## Scope

### 1. Silver layer → `silver/`

One module per target. The schemas tell you most of what is required:

- **`silver_ohlcv`** — enforce numeric types, UTC timestamps, `is_regular_session`
  flag, `bar_missing` detection, `mid`, dedup via `dedup_hash`, `processed_ts`.
  Range rules: `high >= max(open, close)`, `low <= min(open, close)`, `volume >= 0`.
- **`silver_options_quotes`** — parse option symbology into
  underlying/expiry/strike/right, compute `midpoint`, `spread`, `spread_pct`,
  and flag `is_stale` / `is_locked` (bid == ask) / `is_crossed` (bid > ask).
- **`silver_options_trades`** — normalize trades, compute `notional`, aggregate.
  Source is `bronze_options_trades`; `bronze_options_day` (146M rows) is the
  bulk daily aggregate — decide which feeds what and justify it.
- **`silver_sec_sections`** — sections/chunks with `chunk_char_count`, carrying
  `accepted_ts` through. **`accepted_ts` is the information-availability
  timestamp for all SEC features — never use `filing_date`.**
- **`silver_sec_entities`** — extracted entities/XBRL facts with `confidence`
  and `source_chunk_id`. Reuse `api/services/xbrl_*` and
  `api/services/structure_chunker.py`; do not reimplement.
- **`silver_cot_positions`** — from the CFTC tables: normalize TFF participant
  categories to the `*_net` and `*_pct_oi` columns, map `market_code` →
  `mapped_asset`, and set `release_ts` as the official release time.

Dedup rule: use a stable event id where the source provides one, otherwise a
deterministic hash of symbol + event timestamp + price/size/venue. Write that
into `dedup_hash`. Dedup must be idempotent — re-running must not duplicate rows.

Malformed records go to a quarantine table, not silently dropped.
`silver_ohlcv_quarantine` already exists as a STREAMING_TABLE and currently
errors with `STREAMING_TABLE_NEEDS_REFRESH`; report how you handled it rather
than working around it silently.

### 2. Gold layer → `gold/`

- **`gold_ohlcv_features`** — 1/5/15/30m returns, `rvol_*`, `atr_14`,
  `momentum_*`, `rsi_14`, `vwap_deviation`, `relative_volume`,
  `dist_session_high/low`.
- **`gold_options_features`** — put/call volume, IV level/skew/term, spread,
  volume anomaly, OI concentration.
- **`gold_sec_features`** — tone/sentiment, risk-factor change, similarity,
  event flags. Reuse `api/services/sentiment.py`.
- **`gold_cot_features`** — net/relative positioning, rolling percentile,
  z-score, weekly change. Forward-fill only until the next official release.
- **`gold_model_features`** — the PIT-joined matrix keyed by symbol +
  prediction timestamp.
- **`gold_trading_signals`** — leave empty. The ML lane writes it.

### 3. Point-in-time correctness — the part that matters most

Every gold table has an `information_available_ts` column. It is `NOT NULL` in
all six schemas, which tells you it is mandatory.

- For prediction timestamp `t`, an AS-OF join may select **only** records whose
  `information_available_ts <= t`.
- SEC uses `accepted_ts`; COT uses `release_ts`; market features use event/window
  close. **Never backward-fill a future observation.**
- A test must **fail the build** if any joined feature has
  `information_available_ts > prediction_ts`. Include a fixture that
  deliberately injects a leaking row and prove the guard fires. A happy-path-only
  test is a blocking defect.

### 4. Orchestration

A runnable entry point (notebook or module) that executes
bronze → silver → gold in dependency order, is **idempotent**, and reports rows
written per table. If it is a Databricks notebook it must start with
`# Databricks notebook source` and use `# COMMAND ----` cell markers.

---

## Non-goals

- Do not write `gold_trading_signals` (ML lane owns it).
- Do not build Structured Streaming — batch backfill only this slice.
- Do not build the CDF consumer or `analytics_*` tables.
- Do not re-ingest bronze. It is correct and large; read it.
- No frontend, no API routes, no ML models.

## Paths you must NOT touch — other lanes are live

`db/`, `agent/` (Lane A), `ml/`, `tests/ml/` (Lane B), `conftest.py`,
`pytest.ini`, `requirements*.txt`, `README.md` (F0 lane), `.agents/`.
Treat `api/services/*` as **read-only** — import and reuse, do not edit.

## Acceptance criteria

1. Running the orchestrator populates all six `silver_*` tables and five
   `gold_*` tables (not `gold_trading_signals`) with **non-zero** row counts.
   Paste the real `SELECT COUNT(*)` per table. Row counts are the deliverable —
   code that cannot be shown to have written rows does not count.
2. Written columns match `docs/DATA_SCHEMAS.md` exactly. Paste a schema
   comparison.
3. The PIT leakage test exists and **demonstrably fails** on an injected
   leaking row. Paste the failing output, then the passing run.
4. Re-running the orchestrator does not duplicate rows. Paste before/after counts.
5. Data-quality assertions enforced: uniqueness on event keys, not-null on
   symbol/timestamp/price, range constraints, `volume >= 0`, bid/ask sanity.
6. Honest reporting: if a source is too sparse to populate a target, say so with
   numbers rather than emitting an empty table and calling it done.

## When finished

Write your verdict to `.agents/deepseek/VERDICT-silver-gold.md` per
`.agents/PROTOCOL.md`. Report real row counts, not intentions.
