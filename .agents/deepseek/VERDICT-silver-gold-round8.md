# VERDICT: silver-gold round 8 (source availability retained in matrix; self-reconciling build) — DeepSeek
**Status:** APPROVED
**Round:** 8

Implements both build-robustness fixes in `.agents/requests/BUILD-silver-gold-round8.md`.
Feature logic is unchanged (the spine, AS-OF joins, COT warm-up, `is_stale`, and every
source transform are untouched). The two changes are: (1) the matrix now retains each source
row's own availability timestamp in four new columns, so the invariant is exact; (2) the
build now reconciles itself every run via a DELETE + MERGE keyed on a correctly-defined
trading session. Committed on `slice/silver-gold`.

---

## 1. Retain source availability — DONE (additive schema)

`gold/05_gold_model_features.sql` now carries the `information_available_ts` of the exact
source row joined into four new columns: `ohlcv_available_ts`, `options_available_ts`,
`sec_available_ts`, `cot_available_ts`. They are added with an idempotent
`ALTER TABLE ... ADD COLUMNS` in `pipelines/run_silver_gold.py::ensure_model_availability_columns`
(only columns not already present are added; re-runnable). `docs/DATA_SCHEMAS.md` updated to
31 columns.

The matrix invariant in `run_silver_gold.py::run_matrix_invariant` is rewritten to check the
retained columns directly (no more value-matched source back-join):

1. `GREATEST(all non-null *_available_ts) <= prediction_ts`
2. a source's features are non-NULL only if its `*_available_ts` is non-NULL

Live (post-build), every branch returns **0 violating rows**:

```
all source availability <= prediction_ts:  0
options features imply options_available_ts: 0
sec     features imply sec_available_ts:     0
cot     features imply cot_available_ts:     0
```

Availability columns are populated exactly where their features are (coherence = 0):

```
COUNT(ohlcv_available_ts)     = 40,983   (always — OHLCV is the spine)
COUNT(options_available_ts)   = 17,535
COUNT(sec_available_ts)       =  6,420
COUNT(cot_available_ts)       = 40,843
```

**Corruption demo** (as requested): a temp view with one row's `options_available_ts` pushed
`prediction_ts + 1 HOUR` fails the invariant, the real table passes:

```
real table:      GREATEST(*) <= prediction_ts  -> 0 violations
corrupted view:  GREATEST(*) <= prediction_ts  -> 1 violation
```

## 2. Self-reconciling build — DONE (DELETE + MERGE)

`gold/05_gold_model_features.sql` now:

- builds `_silver_gold_daily_base` grouped by **trading session** =
  `DATE(convert_timezone('UTC','America/New_York', feature_ts))` (DST-aware NY session date,
  NOT the UTC date), with `prediction_ts = MAX(information_available_ts)`;
- `DELETE`s, before the MERGE, any target row for a rebuilt `(symbol, session)` whose
  `prediction_ts` differs from the session's new `prediction_ts`
  (`db.prediction_ts <> tgt.prediction_ts`, session derived from
  `DATE(convert_timezone('UTC','America/New_York', tgt.prediction_ts))`);
- MERGEs on `(symbol, prediction_ts)` as before. `--truncate` remains an optional full rebuild.

**Reconciliation test** (live): seeded SPY session 2024-12-26 (NY) with a stale row at
`2024-12-26 21:00 UTC` (`feature_snapshot_id='bogus-stale-seed'`), re-ran the build:

```
before build: 2 rows for SPY/2024-12-26 (correct 01:00 UTC Dec 27 + bogus 21:00 UTC Dec 26)
after build:  1 row  for SPY/2024-12-26 (correct only); bogus-seed COUNT = 0
```

---

## IMPORTANT — row count is now 40,983, not 43,345

The request's verify section expected "43,345 rows". The correct count after this round is
**40,983**, and that is the point of the `"do not group by UTC date"` instruction — it is a
data-correctness improvement, not a regression.

Round 7 grouped the spine by `DATE(feature_ts)` (UTC). Because minute data includes
extended-hours bars up to 20:00 ET (= 00:00/01:00 UTC *next* day in summer/winter), a single
NY trading session's after-hours tail falls on the **next UTC date**, so round 7 emitted two
rows for such sessions. Live comparison of the two groupings:

```
GROUP BY symbol, DATE(feature_ts)                                       -> 43,345  (round 7)
GROUP BY symbol, DATE(convert_timezone('UTC','America/New_York', feature_ts)) -> 40,983  (round 8)
rows where NY date <> UTC date of feature_ts                            -> 231,946 bars
```

The 2,362-row reduction is exactly the split-session artifacts merged back into single
sessions. The table now holds one row per `(symbol, NY trading session)`:

```
COUNT(*)                              = 40,983
COUNT(DISTINCT symbol, prediction_ts) = 40,983   -> EQUAL (no duplicates)
```

## Rebuild — final row counts (normal, non-truncate `--only gold`)

```
gold_ohlcv_features    23,377,478
gold_options_features      19,390
gold_sec_features             128
gold_cot_features           1,464
gold_model_features        40,983   (was 43,345 — see above)
```

## Non-blocking notes

- **`silver_sec_entities` MERGE fails on a non-truncate re-run** (pre-existing, out of scope):
  `silver/06_silver_sec_entities.sql:122-126` keys on `entity_value`, which is not unique per
  `(accession_number, entity_type, entity_key, period_end)` for XBRL facts, so a re-run hits
  `DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE`. The round-8 gold verification was
  therefore run with `--only gold` (silver tables were already populated). Not touched — the
  request scopes round 8 to `gold_model_features` robustness and says not to change feature
  logic; flagging for the coordinator.
- **`gold_sec_features` `.collect()` intermittently returns
  `INVALID_CURSOR.POSITION_NOT_AVAILABLE`** (transient serverless Spark Connect cursor expiry);
  a retry succeeded. Pre-existing, unrelated to round 8.
- `.agents/dispatch.sh` shows a working-tree mode change (100755 → 100644), a WSL/Windows
  filesystem artifact present before this round; left uncommitted.

## Checks run

- `python3 -m pytest tests/gold/test_pit_leakage.py --noconftest -q` → **19 passed** (14 prior + 5 new round-8 tests)
- `python3 -m py_compile pipelines/run_silver_gold.py` → pass
- Live `--counts` (connection smoke) → pass (gold_model_features 43,345 pre-change)
- Live `--only gold` build → pass; final counts pasted above
- Matrix availability invariant → 4×0 violating rows (pasted above)
- Availability-coherence checks → 0/0/0 (pasted above)
- Corruption demo → 1 (corrupted) vs 0 (real) (pasted above)
- Stale-row reconciliation seed test → 2 rows → 1 row after build (pasted above)
