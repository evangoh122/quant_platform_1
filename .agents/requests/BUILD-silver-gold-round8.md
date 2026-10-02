# BUILD-REQUEST: silver-gold — ROUND 8 (make the build self-checking and self-healing)

**Branch:** `slice/silver-gold` · **Builder:** DeepSeek · **Validators:** Claude, then Codex
Read `.agents/codex/VERDICT-silver-gold-round7.md`.

The **live data is correct** (verified: 43,345 rows, 43,345 distinct keys, every
prediction at its last bar's close, COT warm-up NULL). Codex confirmed COT, `is_stale`,
and every earlier fix. Do not change feature logic. Two build-robustness gaps remain.

## 1. Retain source availability in the matrix; check it exactly

The invariant (`pipelines/run_silver_gold.py:187-213`) checks one sampled column per
source (`put_call_ratio`, `sec_sentiment_score`, `cot_lev_money_zscore`) and matches by
value, so (a) rows where that column is NULL but other source columns are populated are
skipped, and (b) a value can match a different historical row.

Fix: add to `gold_model_features` one availability column per source —
`ohlcv_available_ts`, `options_available_ts`, `sec_available_ts`, `cot_available_ts` —
holding the `information_available_ts` of the exact source row joined. This is an
**additive schema change** to an existing table: use `ALTER TABLE ... ADD COLUMNS`,
update `docs/DATA_SCHEMAS.md`, and say so in your verdict.

Then the invariant becomes exact and cheap: for every row,
`GREATEST(all non-null *_available_ts) <= prediction_ts`, and a source's features are
non-null only if its `*_available_ts` is non-null. Show it failing on a deliberately
corrupted copy (e.g. a temp view with one `options_available_ts` pushed past
`prediction_ts`), then passing on the real table.

## 2. The model build must not depend on an operator flag

`gold/05_gold_model_features.sql` MERGEs on `(symbol, prediction_ts)`. If a symbol-day's
`prediction_ts` changes (late bar, or deploying over old data), the new row is inserted
and the old one remains. Truncation currently happens only with `--truncate`.

Fix so the build reconciles itself every run: within the same build, delete target rows
for each `(symbol, trading session)` being rebuilt whose `prediction_ts` is not the
session's new `prediction_ts` — or rebuild the affected sessions with
DELETE-then-INSERT. Define "trading session" correctly (a winter session can end after
midnight UTC; do not group by UTC date). Keep `--truncate` as an optional full rebuild.

Test: seed a session with an old `prediction_ts`, run the build, assert exactly one row
remains for that session with the new `prediction_ts`.

## Verify (live)

After a normal (non-truncate) build: 43,345 rows, 43,345 distinct keys, the four
`*_available_ts` columns populated where their features are, and the exact invariant
passing. Paste counts.

Do not touch `agent/`, `db/`, `api/`, `frontend/`, `ml/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`. **Commit your work.** Write `.agents/deepseek/VERDICT-silver-gold-round8.md`.
