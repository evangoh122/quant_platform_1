# VERDICT: silver-gold round 7 (model-matrix last-bar leak, COT warm-up, is_stale scoping) — DeepSeek
**Status:** APPROVED
**Round:** 7

Fixes the four defects in `.agents/requests/BUILD-silver-gold-round7.md`. Committed as
`518cc60` on `slice/silver-gold`, finishing the partial edits preserved in `3af8b1a`
(`wip(silver-gold): round-7 edits in progress`). The WIP edits to the four SQL files were
reviewed and kept as-is (they were correct); I extended the matrix invariant to cover all
four sources and added a portable test for the OHLCV back-join, then rebuilt the affected
tables live and verified.

---

## 1. Model matrix last-bar leak (critical) — FIXED

`gold/05_gold_model_features.sql:37` now sets `prediction_ts = MAX(information_available_ts)`
(the last bar's **availability**, i.e. its `feature_ts + 1 minute`) and the OHLCV join keys
on `f.information_available_ts = db.prediction_ts` (`:48`) instead of `f.feature_ts`. The old
code set `prediction_ts = MAX(feature_ts)` (the last bar's **start**) and joined on
`f.feature_ts`, so every matrix row consumed its final bar 60s before that bar was observable.

Live proof (after rebuild), per `gold_ohlcv_features`:

```
spine (symbol, DATE(feature_ts)):  n = 43,345
  rows where MAX(information_available_ts) = MAX(feature_ts) + 60s:  43,345 / 43,345
```

Every matrix row's `prediction_ts` is now exactly the last bar's `feature_ts + 1 minute`.

**MERGE-key change handled by a clean rebuild.** The key `(symbol, prediction_ts)` shifted by
+60s, so a plain re-run would have inserted new rows beside the old leaking rows. I
`TRUNCATE`d `gold_model_features` and re-ran the MERGE once.

Duplicate proof (exactly as the request specifies — NOT `COUNT(DISTINCT symbol, DATE(...))`,
which is 39,202 because 4,143 symbol-days legitimately carry two rows when a session's last
bar falls after midnight UTC):

```
(a) COUNT(*)                                  = 43,345
    COUNT(DISTINCT symbol, prediction_ts)     = 43,345   -> EQUAL (no duplicates)
(b) total rows                                = 43,345   (unchanged)
(c) COUNT(DISTINCT symbol, DATE(prediction_ts)) = 39,202 (the 4,143 legitimate two-row symbol-days)
```

## 2. Build invariant checks the model matrix — FIXED

`pipelines/run_silver_gold.py::run_matrix_invariant` (added in the WIP commit, extended here)
now asserts, per `gold_model_features` row, that every contributing source row is available
at/<= `prediction_ts`, by joining back to each source:

- **ohlcv** — back-join on `information_available_ts = prediction_ts` plus `return_1m`/`rsi_14`
  value match; a missing bar means the row used a bar not yet available.
- **options / sec / cot** — anti-join: a non-NULL feature value must be traceable to a source
  row with `information_available_ts <= prediction_ts`.

It is wired into both `run_checks` (`--check`) and the normal gold build path.

**Failing on the current table, passing after** (live):

```
BEFORE (table as found — OHLCV already availability-keyed by the prior WIP run, but the
        matrix's COT columns were stale, carrying round-6 partial-window z-scores):
  ohlcv   bar available at prediction_ts:        0
  options feature available <= prediction_ts:    0
  sec     feature available <= prediction_ts:    0
  cot     feature available <= prediction_ts: 8778  <-- FAILS (RuntimeError)

AFTER (rebuild):
  ohlcv / options / sec / cot: all 0                    <-- PASSES
```

The 8,778 pre-rebuild violations are exactly the rows whose `cot_lev_money_zscore` came from
the round-6 COT build (partial-window values for the first 51 reports) and were no longer
present in the warm-up-gated COT source — a genuine "value not available as-of prediction_ts".

The OHLCV branch's ability to catch the last-bar-start leak (rather than the COT staleness it
happened to trip on first) is proven by the new portable test
`test_matrix_invariant_catches_last_bar_start_leak`: a leaked row (`prediction_ts` = bar
START) is flagged (1 violating row) and the availability-keyed row passes (0).

## 3. COT 52-report warm-up — FIXED

`gold/04_gold_cot_features.sql` gates the 52-week percentile and z-score (and the derived
`crowding_score` / `regime_label`) on a full window: `COUNT(*) OVER (ROWS BETWEEN 51 PRECEDING
AND CURRENT ROW) AS n_52w`, used only when `n_52w >= 52`, else NULL. The first 51 reports of
each `mapped_asset` are now NULL. Live verification (after rebuild):

```
per mapped_asset (6 assets x 244 reports): first 51 reports non-NULL z-score = 0
report 52 of equity_index: lev_money_zscore_52w = 0.3869... (non-NULL)
```

## 4. `is_stale` point-in-time scoping — FIXED

`silver/03_silver_options_quotes.sql` scopes `snapshot_ts = MAX(participant_ts) OVER
(PARTITION BY ingest_ts)` — the quote's own ingest batch — instead of the whole-table
`MAX(participant_ts) OVER ()`. An appended future snapshot can no longer retroactively
re-stale earlier batches. (Current data is a single batch: `ingest_ts` = `participant_ts` =
`2026-09-02 00:36:24.930278`, so all 61,882 rows are `is_stale = false` under both old and
new definitions; the fix is forward-looking.)

---

## Rebuild — row counts

Re-ran `silver_options_quotes`, `gold_cot_features`, and `TRUNCATE` + `gold_model_features`
(serverless Spark, `databricks-connect`, profile `evangohsg`):

```
                              BEFORE       AFTER        delta
silver_options_quotes          61,882       61,882         0
gold_cot_features               1,464        1,464         0
gold_model_features            43,345       43,345         0
gold_ohlcv_features              n/a    23,377,478   (untouched)
gold_options_features            n/a        19,390   (untouched)
gold_sec_features                n/a           128   (untouched)
```

## Non-blocking notes

- `gold_model_features` does not retain source availability timestamps, so the matrix
  invariant relies on value-matched join-backs. For options/sec/cot the value is copied
  verbatim from the source, so `IS NOT DISTINCT FROM` is exact; a value collision across
  days only ever produces a false negative (an identical value is harmless), never a false
  positive.
- `prediction_ts` for a 960-bar symbol equals the next UTC day's first bar START (e.g. the
  23:59 bar's availability is 00:00 next day, which is also the next bar's start). This is
  expected and is NOT a leak; the definitive check is the 60s-offset proof in §1.
- Two silver test modules (`test_silver_index_stats.py`, `test_silver_ohlcv_quality.py`)
  still import the removed `db.database` and fail at collection — pre-existing, unrelated to
  this round, and `db/` is out of scope (do-not-touch).

## Checks run

- `python3 -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → **14 passed**
- `python3 -m pytest tests/silver/test_silver_conversions.py -v` → **18 passed**
- `python3 -m pytest tests/silver/ -v` → 2 collection errors (removed `db.database`; pre-existing)
- Live rebuild + matrix invariant: BEFORE cot 8,778 → FAILS; AFTER all 0 → PASSES (pasted above)
- Duplicate proof `COUNT(*) = COUNT(DISTINCT symbol,prediction_ts)` = 43,345 (pasted above)
- 60s-offset proof 43,345/43,345 (pasted above)
- COT warm-up: first-51 non-NULL z-score = 0 across all 6 `mapped_asset`s (pasted above)
