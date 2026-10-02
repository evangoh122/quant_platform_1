# VERDICT: silver-gold round 6 (minute-bar availability) — DeepSeek
**Status:** APPROVED
**Round:** 6

Fixes the defect in `.agents/requests/BUILD-silver-gold-round6.md`: `gold_ohlcv_features`
stamped `information_available_ts = event_ts`, but Polygon minute bars are labelled at
their **START** (`event_ts` = `[t, t+1min)`), so a bar's close is known only at
`event_ts + 1 minute`. All 23,377,478 rows claimed availability one bar early.
Committed as `fbe9b69` on `slice/silver-gold`.

---

## 1. Defect — minute bars stamped at their start — FIXED

`gold/01_gold_ohlcv_features.sql` now derives availability from `timespan` rather than
copying `event_ts` verbatim:

```sql
CASE timespan
  WHEN 'minute' THEN event_ts + INTERVAL 1 MINUTE
  ELSE event_ts
END AS information_available_ts
```

The interval is computed once in the `lagged` CTE (where `timespan` is natively
available from `silver_ohlcv`) and carried through `returns`/`feats` to the final
SELECT. The `WHERE timespan = 'minute'` filter means only minute bars flow into the
table, so the `ELSE event_ts` branch is unreachable today but documents that any
non-minute bar keeps its provider stamp rather than blindly gaining `+1 minute`.

The stale header comment at `:7` ("information_available_ts = event_ts (the bar close
is when the bar becomes observable)") is corrected to state the Polygon START-stamp
convention and the `event_ts + bar interval` rule.

`gold/05_gold_model_features.sql`'s PIT-rule comment ("ohlcv: information_available_ts
= bar close (== prediction_ts)") is also corrected: ohlcv is joined directly on
`feature_ts == prediction_ts` (not AS-OF on info_ts), and its `information_available_ts`
is `feature_ts + bar interval`.

## 2. Availability-rule audit (every bar-stamped source)

| Source | Availability rule | Verdict |
| :-- | :-- | :-- |
| `gold_ohlcv_features` (from `silver_ohlcv`, `timespan='minute'`) | `event_ts` = bar **start** | **FIXED** → `event_ts + INTERVAL 1 MINUTE` (timespan-derived) |
| `gold_options_features` (from `bronze_options_day`) | session close + 30m buffer (round 5) | SAFE |
| `gold_cot_features` (from `silver_cot_positions`) | `release_ts` | SAFE |
| `gold_sec_features` (from `silver_sec_sections`) | `accepted_ts` | SAFE |
| `bronze_ohlcv_day` | daily OHLCV rollup | **NOT USED** — no silver/gold transform reads it (re-verified: grep across `gold/`, `silver/`, `pipelines/` finds only `docs/DATA_SCHEMAS.md` and `notebooks/archive/`). Daily bars never reach gold; `gold_ohlcv_features` filters `timespan='minute'`. |

No other transform sets availability from a bar's own start-of-window stamp.

## 3. Availability invariant extended — fails on current table, passes after

`pipelines/run_silver_gold.py::run_availability_invariant` gained a third check
(`ohlcv minute info_ts >= event_ts + 1 minute`), and the `run_checks` DQ assertion was
updated from `info_ts == feature_ts` to `info_ts == feature_ts + INTERVAL 1 MINUTE`.

```
BEFORE (current table, pre-rebuild):
  ohlcv minute info_ts >= event_ts + 1 minute: 23,377,478 violating rows   <- FAILS

AFTER (rebuild):
  ohlcv minute info_ts >= event_ts + 1 minute: 0 violating rows            <- PASSES
  options info_ts >= session close:            0 violating rows
  cot info_ts >= report_date:                  0 violating rows
```

`tests/gold/test_pit_leakage.py` gained two round-6 tests:
- `test_ohlcv_availability_derived_from_timespan` — guard: no `event_ts AS information_available_ts`; requires `CASE timespan` and `event_ts + INTERVAL 1 MINUTE`.
- `test_minute_availability_invariant_catches_start_of_bar_stamp` — the invariant flags `info_ts = event_ts` (1 violating row) and passes `info_ts = event_ts + 1 min` (0).

## 4. Rebuild — row counts unchanged, availability corrected

Re-ran the `gold_ohlcv_features` and `gold_model_features` MERGE paths (serverless
Spark, `databricks-connect`, profile `evangohsg`):

```
                          BEFORE           AFTER
gold_ohlcv_features       23,377,478       23,377,478   (delta 0)
gold_model_features           43,345           43,345   (delta 0)
```

Post-rebuild `information_available_ts - feature_ts` distribution:

```
BEFORE:   0 secs   23,377,478 rows   (one bar early — the leak)
AFTER:   60 secs   23,377,478 rows   (expected 60s)
```

## Non-blocking notes

- `gold_model_features.prediction_ts` is still the last minute bar's **start**
  timestamp, so the ohlcv feature at that spine row is now flagged available at
  `prediction_ts + 1 min`. This does not change the join (ohlcv is joined on
  `feature_ts`, not info_ts), but it means a strictly-literal PIT consumer reading
  `information_available_ts` for the spine bar would see it as one minute in the
  future. Shifting `prediction_ts` to the bar close is a larger semantic change and
  is out of scope for this narrow round; flagged for the coordinator.
- `ontology/join_hints.yaml` and `ontology/business_terms.yaml` were updated to keep
  the documented PIT rule consistent with the fix (no functional impact).

## Checks run

- `python3 -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → **10 passed**
- `python3 -m py_compile pipelines/run_silver_gold.py` → OK
- `DATABRICKS_PROFILE=evangohsg python3 pipelines/run_silver_gold.py --check` → 8/8 PIT/DQ clean + availability invariant 0/0/0
- Pre-rebuild minute invariant → 23,377,478 violating rows; post-rebuild → 0 (pasted above)
- Rebuild counts 23,377,478 / 43,345 (delta 0); `info_ts - feature_ts` 0s → 60s (pasted above)
