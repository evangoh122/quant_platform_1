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

`gold_trading_signals` is left empty (0 rows) per the request — the ML lane owns it.
`silver_ohlcv_quarantine_batch` is 0 rows because the MVP-universe liquid names
have clean OHLCV (no NULL/range/negative bars, verified below).

## What was executed and how

Serverless Spark via `databricks-connect`
(`DatabricksSession.builder.serverless(True).getOrCreate()`). The orchestrator is
`pipelines/run_silver_gold.py`: it registers the MVP universe from
`config/universe.yaml` as a temp view and runs the 12 transforms in dependency
order. Every symbol-keyed transform filters `symbol IN (SELECT symbol FROM
universe)` — no hardcoded ticker lists in transform code. `config/universe.yaml`
has 39 liquid names including the required SPY, QQQ, NVDA, AAPL, MSFT, AMZN, META,
AMD, GOOGL, TSLA.

Round-1 drafts needed three fixes before they would actually run:

1. **`silver_ohlcv` dedup** — bronze carries duplicate `(symbol, event_ts,
   timespan)` bars from multiple sources with identical OHLCV; the plain MERGE
   hits `DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE` on re-run. Fixed
   with `ROW_NUMBER() OVER (PARTITION BY symbol, event_ts, timespan ORDER BY
   ingest_ts DESC, source)` and `rn = 1` in the source.
2. **`gold_sec_features`** — the SQL `regexp_extract_all` bag-of-words failed at
   runtime (`INVALID_PARAMETER_VALUE.REGEX_GROUP_INDEX`). Replaced with a PySpark
   module `gold/gold_sec_features.py` that reuses
   `api.services.sentiment.count_sentiment` + `tokenize` against a bundled
   Loughran-McDonald dictionary (`data/sentiment_dict/lm_word_lists.json`),
   exactly as the round-2 request specifies. 128 filings scored.
3. **`gold_cot_features`** — `RANK()/COUNT(*) OVER (... ROWS 51 PRECEDING)` is an
   invalid frame for ranking functions; switched to an unbounded frame.

## Acceptance criteria

1. **Non-zero row counts** — table above, pasted from actual `SELECT COUNT(*)`
   via `python pipelines/run_silver_gold.py --counts`.
2. **`config/universe.yaml`** exists (39 names); `config/universe.py` loads it;
   every symbol-keyed silver/gold transform reads its filter from it. COT is
   regime-level (`mapped_asset`), so it is not symbol-filtered.
3. **Schema conformance** — `DESCRIBE` of `silver_ohlcv` (15 cols),
   `gold_sec_features` (13 cols) and `gold_model_features` (27 cols) match
   `docs/DATA_SCHEMAS.md` column-for-column; the transforms write exactly the
   pre-created target columns.
4. **PIT leakage test fires** — see below.
5. **Idempotency** — see below.
6. **Committed** — `94f0fbc` (build) + this verdict.

## PIT leakage — failing run, then passing run

Direct demonstration against `gold/pit_guard.py`:

```
=== PASSING run (no leak) ===
validate_no_lookahead(...) -> no exception, OK

=== FAILING run (injected leaking row) ===
LookaheadLeakError raised as expected: PIT leakage: 1 joined feature(s) have
information_available_ts > prediction_ts=2026-09-02 16:00:00+00:00
leaking rows found: [2026-09-02 16:05:00+00:00]
```

`python -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → **6 passed**
(includes `test_leak_guard_fires_on_injected_leaking_row` and the `<=` boundary
test). `gold_model_features` joins each source AS-OF with
`information_available_ts <= prediction_ts` (SEC=`accepted_ts`, COT=`release_ts`,
OHLCV=`event_ts`/bar close, options=`MAX(participant_ts)`).

## Idempotency (before / after re-run)

Re-ran `silver_ohlcv`, `gold_cot_features`, `gold_sec_features`,
`gold_model_features` (MERGE-on-key) with no truncate; counts identical:

```
silver_ohlcv        23420557 -> 23420557   (delta 0)
gold_cot_features       1464 ->    1464   (delta 0)
gold_sec_features         128 ->     128   (delta 0)
gold_model_features     14958 ->   14958   (delta 0)
```

## Checks run

- `python pipelines/run_silver_gold.py --counts` → 12 targets listed (pass)
- `python pipelines/run_silver_gold.py --check` → all 0: options/sec/cot info_ts
  non-null 0, ohlcv info_ts==feature_ts 0, model snapshot_id null 0, silver_ohlcv
  range violations 0, null prices 0, cot null market_code 0 (pass)
- `python -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → 6 passed
- `DESCRIBE silver_ohlcv / gold_sec_features / gold_model_features` → matches
  `docs/DATA_SCHEMAS.md`
- idempotency re-run → counts unchanged

## Non-blocking notes

- **`silver_ohlcv_quarantine` (STREAMING_TABLE)** errors with
  `STREAMING_TABLE_NEEDS_REFRESH` on batch write; handled by writing to a new
  managed table `silver_ohlcv_quarantine_batch` (documented in
  `silver/02_silver_ohlcv_quarantine.sql`). It is empty for the universe.
- **`gold_options_features` = 12 rows** — `bronze_options_quotes` is a single-day
  snapshot of 12 underlyings. `put_volume`, `call_volume`, `put_call_ratio`,
  `iv_atm`, `iv_25d_put`, `iv_25d_call`, `iv_skew`, `iv_term_slope`,
  `oi_concentration`, `net_delta_exposure` are **real and populated**
  (`implied_volatility`/`delta` are present in 56,004 / 55,533 source rows).
  `avg_spread_pct` is NULL because `bid`/`ask`/`midpoint` are entirely NULL in the
  source; `volume_anomaly_zscore` is NULL because a z-score cannot be computed
  from a single day. Reported honestly, not fabricated.
- **`gold_sec_features`** — 128 filings (16 tickers × 8 filings, 10-K/10-Q only).
  `material_event_flag` is FALSE everywhere because the SEC source holds no 8-K
  filings in the universe. `risk_factor_change`/`filing_similarity` are NULL for
  each ticker's first filing (no prior to compare).
- **`gold_model_features`** — `sec_sentiment_score` is populated only for AMD and
  NVDA (the only universe symbols with SEC coverage; the SEC source ingested 16
  semiconductor tickers). Other symbols are NULL, which is honest sparsity, not a
  defect. `cot_*` features are populated at the `equity_index` regime level.
- **`prediction_ts` time-of-day** — the minute session in this data spans
  `16:00 UTC → 07:59 UTC` (next day), so `prediction_ts = MAX(feature_ts)` per day
  lands at ~07:59 UTC, not the US close. PIT (`<=`) is still enforced regardless;
  `silver_ohlcv.is_regular_session` is available if a session-only close is wanted.
- **LM dictionary provenance** — `data/sentiment_dict/lm_word_lists.json` is the
  Loughran-McDonald (2020) list. Its `negative` list matches the canonical
  (~2,340); its `uncertainty` list (2,753 entries) is anomalously large (inherited
  from the reference copy). `tone_uncertainty` should be treated with caution;
  `sentiment_score`/`tone_positive`/`tone_negative` are positive/negative-driven.
- **Concurrency** — a concurrent round-2 dispatch committed the build (`94f0fbc`)
  and an earlier verdict (`eb3a2bc`) while this dispatch was executing. I
  independently re-verified the row counts, PIT guard, and idempotency above; the
  committed state is coherent. This verdict supersedes `eb3a2bc` and corrects two
  of its inaccuracies: (a) `iv_*`/`iv_skew`/`iv_term_slope` **are** populated, and
  (b) `prediction_ts` is ~07:59 UTC, not 23:59.
