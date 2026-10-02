# BUILD-REQUEST: silver-gold — ROUND 2

**Branch:** `slice/silver-gold` (continue; round-1 drafts are committed at `041e140`)
**Supersedes:** `BUILD-silver-gold.md` — read that for schemas and layer
requirements, but **the execution approach below replaces its SQL-only
instruction.**

## What happened in round 1

You drafted 7 silver + 2 gold SQL transforms, then hit the dispatch timeout
mid-edit. **Nothing was executed.** All twelve target tables are still at
**0 rows**, which I verified directly.

> **Row counts are the deliverable.** SQL files that have never run are worth
> nothing to this slice. Prioritise *executing* over *writing more transforms*.

---

## Change 1 — you now have real Spark. Use it.

`databricks-connect` 19.2.0 is installed and **serverless compute works**. I
verified it end to end:

```python
from databricks.connect import DatabricksSession
spark = DatabricksSession.builder.serverless(True).getOrCreate()
spark.table("bootcamp_students.evangoh_capstone.bronze_ohlcv").count()
# -> 72678354
```

This supersedes the round-1 constraint that you must use SQL through the
Statement Execution API. Both paths now work — choose per transform:

- **PySpark is required** for `gold_sec_features`: it needs
  `api/services/sentiment.py`, which is Python and cannot be expressed in SQL.
  Same for anything reusing `api/services/xbrl_*` or `structure_chunker.py`.
- **SQL is fine** for the mechanical silver transforms you already drafted —
  do not rewrite working SQL just because PySpark is now available.

Note: `pyspark` was uninstalled because `databricks-connect` refuses to run
alongside it and ships its own (4.4.0.dev0). `import pyspark` still works.

## Change 2 — filter to the MVP universe

`bronze_ohlcv` contains **11,617 distinct symbols** and `config/tickers.yaml`
lists **12,400 tickers** grouped by industry — effectively the whole US market.
The rubric specifies an MVP universe of "approximately 20-50 highly liquid U.S.
equities and ETFs (for example SPY, QQQ, NVDA, AAPL, MSFT, AMZN, META, AMD and
similar names)" and says it must be configuration-driven.

Transforming all 11,617 symbols would produce tens of millions of gold feature
rows, cost a lot, and is not what the proposal describes.

**Create `config/universe.yaml`** with ~30 liquid names (include at minimum
SPY, QQQ, NVDA, AAPL, MSFT, AMZN, META, AMD, GOOGL, TSLA) and have **every**
silver and gold transform read its symbol filter from that file. No hardcoded
ticker lists in transform code. Keep `tickers.yaml` untouched — it is the
ingestion-side whole-market list.

---

## Order of work — do not deviate

Work incrementally and **verify row counts after each step**. A partial result
that is real beats a complete result that was never run.

1. **Execute the 7 silver transforms you already wrote.** Fix whatever breaks.
   After each, run `SELECT COUNT(*)` and record it.
2. **Stop and report silver counts** before starting more gold work.
3. `gold_ohlcv_features` and `gold_options_features` — you have drafts; execute them.
4. `gold_cot_features` — from `silver_cot_positions`.
5. `gold_sec_features` — PySpark, reusing `api/services/sentiment.py`.
6. `gold_model_features` — the PIT-joined matrix. This is the one that matters
   most; see the PIT rules in the round-1 request.
7. `gold_trading_signals` — **leave empty**, the ML lane owns it.

If you run short on time, a correct subset with real row counts and an honest
list of what is not done is the right outcome. **Do not claim completion you
cannot show counts for.**

## Still required from round 1

- Schemas must match `docs/DATA_SCHEMAS.md` exactly — the targets already exist.
- `information_available_ts` is `NOT NULL` in all six gold tables. SEC uses
  `accepted_ts`, COT uses `release_ts`, market features use event/window close.
- The PIT leakage test must **fail** on a deliberately injected leaking row.
  Paste the failing run, then the passing one.
- Idempotency: re-running must not duplicate rows. Paste before/after counts.
- `bronze_cot` is empty — source COT from `bronze_cftc_fut` / `bronze_cftc_com`.
- `silver_ohlcv_quarantine` is a STREAMING_TABLE that errors with
  `STREAMING_TABLE_NEEDS_REFRESH`; report how you handled it.

## Acceptance criteria

1. **Real, non-zero row counts** for every table you claim to have populated,
   pasted as actual query output.
2. `config/universe.yaml` exists and every transform reads its filter from it.
3. Schema conformance shown for at least one silver and one gold table.
4. PIT leakage test demonstrably fires.
5. Idempotency shown by before/after counts.
6. **Commit before you finish.** Both previous dispatches ended uncommitted and
   I had to commit on your behalf.

## Do not touch

`db/`, `agent/` (Lane A), `ml/`, `tests/ml/` (Lane B), `conftest.py`,
`pytest.ini`, `requirements*.txt`, `README.md` (F0 lane), `.agents/`.
`api/services/*` is **read-only** — import and reuse, never edit.

## When finished

`.agents/deepseek/VERDICT-silver-gold.md` per `.agents/PROTOCOL.md`, leading
with the row-count table.
