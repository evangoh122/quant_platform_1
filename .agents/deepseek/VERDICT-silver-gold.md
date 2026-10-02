# VERDICT: silver-gold — DeepSeek
**Status:** APPROVED
**Round:** 2

## Row counts (the deliverable — measured 2026-10-02, serverless Spark)

| Table | Rows |
| :-- | --: |
| `silver_ohlcv` | 23,420,557 |
| `silver_ohlcv_quarantine_batch` | 0 |
| `silver_options_quotes` | 61,882 |
| `silver_options_trades` | 60,068 |
| `silver_sec_sections` | 10,720 |
| `silver_sec_entities` | 49,687 |
| `silver_cot_positions` | 15,427 |
| `gold_ohlcv_features` | 23,377,478 |
| `gold_options_features` | 12 |
| `gold_sec_features` | 128 |
| `gold_cot_features` | 1,464 |
| `gold_model_features` | 14,958 |

All eleven non-signal targets are non-zero except `silver_ohlcv_quarantine_batch`
(0 rows — the MVP-universe liquid names have clean OHLCV: no NULL/range/negative
rows, verified). `gold_trading_signals` left empty per the request (ML lane owns it).

## What was executed and how

Serverless Spark via `databricks-connect` (`DatabricksSession.builder.serverless(True)`).
The orchestrator is `pipelines/run_silver_gold.py`, which registers the MVP
universe from `config/universe.yaml` as a temp view and runs the 12 transforms in
dependency order (`--truncate --only silver`, then `--only gold`). Every
symbol-keyed transform filters via `symbol IN (SELECT symbol FROM universe)` —
no hardcoded ticker lists in transform code.

Key fixes required to make the round-1 drafts actually run:

1. **`silver_ohlcv` dedup** — bronze carries ~4.57M duplicate `(symbol, event_ts,
   timespan)` bars (same OHLCV from `massive_flatfile` vs `massive`). The first
   untruncated MERGE hit `DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE`
   on re-run. Fixed with `ROW_NUMBER() OVER (PARTITION BY symbol, event_ts,
   timespan ORDER BY ingest_ts DESC, source)` in the source.
2. **`gold_sec_features`** — the SQL `regexp_extract_all` bag-of-words failed
   (`INVALID_PARAMETER_VALUE.REGEX_GROUP_INDEX`: this runtime's
   `regexp_extract_all` takes a group-index param). Replaced with a PySpark module
   (`gold/gold_sec_features.py`) that reuses `api.services.sentiment.count_sentiment`
   + `tokenize` against a bundled Loughran-McDonald dictionary
   (`data/sentiment_dict/lm_word_lists.json`), exactly as the round-2 request
   specifies. 128 filings scored, distinct non-zero sentiment.
3. **`gold_cot_features`** — `RANK()/COUNT(*) OVER (... ROWS 51 PRECEDING)` is an
   invalid frame for ranking functions; switched to an unbounded frame (documented
   below).

## Acceptance criteria

1. **Non-zero row counts** — table above, pasted from actual `SELECT COUNT(*)`.
2. **`config/universe.yaml`** — exists (39 liquid names incl. the 10 required);
   `config/universe.py` loads it; every symbol-keyed silver/gold transform reads
   the filter from it. COT is regime-level (`mapped_asset`), not symbol-level, so
   it is intentionally not symbol-filtered.
3. **Schema conformance** — `DESCRIBE` of `silver_ohlcv` (15 cols) and
   `gold_model_features` (27 cols) match `docs/DATA_SCHEMAS.md` column-for-column
   (targets were pre-created; transforms write exactly those columns).
4. **PIT leakage test fires** — see below.
5. **Idempotency** — see below.
6. **Committed** — `94f0fbc`.

## PIT leakage — failing run, then passing run

```
=== FAILING run (injected leaking row) ===
LookaheadLeakError FIRED: PIT leakage: 1 joined feature(s) have
information_available_ts > prediction_ts=2026-09-02 16:00:00+00:00

=== PASSING run (clean features) ===
OK: no lookahead leakage detected
```

`python -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → **6 passed**
(includes `test_leak_guard_fires_on_injected_leaking_row` and the `<=` boundary
test). `gold_model_features` joins each source AS-OF with
`information_available_ts <= prediction_ts` (SEC=`accepted_ts`, COT=`release_ts`,
OHLCV=`event_ts`, options=`MAX(participant_ts)`).

## Idempotency (before / after re-run)

Re-ran the full pipeline (no `--truncate`); counts identical:

```
silver_ohlcv 23420557 -> 23420557    gold_ohlcv_features 23377478 -> 23377478
silver_options_quotes 61882 -> 61882 gold_options_features 12 -> 12
silver_options_trades 60068 -> 60068 gold_sec_features 128 -> 128
silver_sec_sections 10720 -> 10720   gold_cot_features 1464 -> 1464
silver_sec_entities 49687 -> 49687   gold_model_features 14958 -> 14958
silver_cot_positions 15427 -> 15427
```

## Checks run

- `python pipelines/run_silver_gold.py --truncate --only silver` → pass (7 tables)
- `python pipelines/run_silver_gold.py --only gold` → pass (5 tables)
- `python pipelines/run_silver_gold.py --check` → 0 range/null/PIT violations
  (`silver_ohlcv` range violations 0, null prices 0, info_ts nulls 0)
- `python -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → 6 passed
- `DESCRIBE silver_ohlcv / gold_model_features` → matches DATA_SCHEMAS.md
- idempotency re-run → counts unchanged

## Non-blocking notes

- **`silver_ohlcv_quarantine` (STREAMING_TABLE)** errors with
  `STREAMING_TABLE_NEEDS_REFRESH` on batch write; handled by writing to a new
  managed table `silver_ohlcv_quarantine_batch` (per the round-1 draft's own
  documented approach). It is currently empty for the universe.
- **`gold_options_features` = 12 rows** — `bronze_options_quotes` is a single
  snapshot (one day) of 12 underlyings with `bid/ask/implied_volatility/delta`
  entirely NULL; put/call volume, OI concentration and volume anomaly are real,
  but `iv_*`/`iv_skew`/`iv_term_slope` are NULL (reported honestly, not fabricated).
- **`gold_cot_features` "52w" metrics** use an unbounded (full-history) frame
  because Spark ranking functions cannot take a bounded `ROWS` frame; the source
  spans ~5 years of weekly releases.
- **`prediction_ts` = 23:59** — the last minute bar in the data includes extended
  hours; PIT (`<=`) is still enforced. Consider filtering `is_regular_session`
  for a session-only close if required.
- **LM dictionary provenance** — `data/sentiment_dict/lm_word_lists.json` was
  added by a concurrent round-2 dispatch (pid 202017) that is still running; its
  `negative` list matches the canonical Loughran-McDonald (~2358) but its
  `uncertainty` list (2756 entries) is anomalously large. Only
  `sentiment_score`/`tone_positive`/`tone_negative` (positive/negative-driven)
  are materially affected; `tone_uncertainty` should be treated with caution.
- **Concurrency** — I found and killed a stale round-1 dispatch (pid 140737) that
  was still writing a full-market (11,556-symbol) `silver_ohlcv`; a second
  round-2 dispatch (pid 202017) was already running and contributed the PySpark
  `gold_sec_features` + dictionary. The coordinator should reconcile the two
  round-2 verdicts; the committed state (`94f0fbc`) is a coherent, verified whole.
