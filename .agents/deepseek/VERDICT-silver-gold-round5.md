# VERDICT: silver-gold round 5 (options availability leak) — DeepSeek
**Status:** APPROVED
**Round:** 5

Fixes the three defects in `.agents/requests/BUILD-silver-gold-round5.md`:
the daily-options availability timestamp was the provider's **start-of-day** stamp
(04:00/05:00 UTC = midnight New York) rather than the session close, so a same-day
intraday prediction saw the whole day's options volume hours before it existed.
Committed as `d7871a7` on `slice/silver-gold`.

---

## 1. Defect 1 — daily options availability (critical) — FIXED ✅

`gold/02_gold_options_features.sql:70-73` now computes availability as **session
close (16:00 America/New_York) + publication buffer**, DST-aware:

```sql
convert_timezone('America/New_York', 'UTC',
    to_timestamp(concat(cast(event_date AS STRING), ' 16:00:00')))
  + make_interval(0, 0, 0, 0, 0, opt_pub_buffer_minutes, 0)
```

The buffer is a **named constant** `opt_pub_buffer_minutes INT DEFAULT 30`
(`DECLARE OR REPLACE VARIABLE` at the top of the file).

**Deviation from the request (documented in the SQL header):** the request
suggested `to_utc_timestamp(<d> 16:00, 'America/New_York')`, but on this
workspace `to_utc_timestamp` is deprecated and double-converts via the session
timezone, returning **04:00/05:00 UTC — the same start-of-day bug**:

```
to_utc_timestamp('2024-09-04 16:00:00','America/New_York') -> 2024-09-05 04:00:00   (WRONG)
convert_timezone('America/New_York','UTC', ...)            -> 2024-09-04 20:00:00   (summer, EDT)
convert_timezone('America/New_York','UTC', ...)            -> 2024-12-15 21:00:00   (winter, EST)
```

`convert_timezone(source, target, ts)` is the ANSI-standard DST-aware function and
yields exactly the coordinator's expected values.

**Before / after the rebuild:**

```
              info_ts time-of-day          rows
BEFORE        04:00:00                     12,859
              05:00:00                      6,531
AFTER         20:30:00 (summer)            12,859
              21:30:00 (winter)             6,531
```

Row counts unchanged: `gold_options_features` 19,390 → 19,390;
`gold_model_features` 43,345 → 43,345.

---

## 2. Availability-rule audit (every daily/period aggregate)

| Source | Availability rule | Verdict |
| :-- | :-- | :-- |
| `gold_options_features` (from `bronze_options_day`) | `MAX(event_ts)` = 04:00/05:00 start-of-day | **FIXED** → session close + 30m buffer |
| `gold_ohlcv_features` (from `silver_ohlcv`, `timespan='minute'`) | `event_ts` = bar close | SAFE — minute bars are point-in-time |
| `bronze_ohlcv_day` | daily OHLCV rollup | **NOT USED** — no silver/gold transform reads it (grep: only `notebooks/archive/00_project_setup.py`). The daily OHLCV bars never reach gold; `gold_ohlcv_features` filters `timespan='minute'`. |
| `gold_cot_features` (from `silver_cot_positions`) | `release_ts` | SAFE — `release_ts = report_date + 3 days` at 15:30 ET (19:30/20:30 UTC), the official CFTC release, **not** `report_date`. Verified: `datediff(release_ts, report_date) = 3` for all rows; tod ∈ {19:30, 20:30}. |
| `gold_sec_features` (from `silver_sec_sections`) | `accepted_ts` | SAFE — SEC acceptance timestamp (PIT key), never `filing_date`. |

Only `gold_options_features` carried a start-of-window stamp. No other daily or
period aggregate marks the start of its window.

---

## 3. Defect 2 — `is_stale` used the day's last quote — FIXED ✅

`silver/03_silver_options_quotes.sql:49` was `MAX(participant_ts) OVER
(PARTITION BY underlying)` — the latest quote of the whole day.

I inspected the source: `bronze_options_quotes` is a **single snapshot** — all
61,882 rows carry one `participant_ts` (`2026-09-02 00:36:24.930278`, verified).
So I chose the **snapshot-time definition** (the request's second option) and
documented it in the header: `is_stale` is compared against `snapshot_ts =
MAX(participant_ts) OVER ()` — the single capture instant — not a per-underlying
whole-day MAX. A quote is stale iff its `participant_ts` lags the snapshot by
more than 15 minutes. Result is unchanged (all `false`, 61,882 rows) but the
semantics are now correct and documented; a future multi-timestamp snapshot can
no longer mis-flag earlier quotes.

---

## 4. Defect 3 — PIT test extended — DONE ✅

**Availability invariant (SQL assertion, fails the build):**
`pipelines/run_silver_gold.py` gained `run_availability_invariant(spark)`, run
after every gold build (and via `--check`). It raises `RuntimeError` if any
`gold_options_features` row has `information_available_ts < session close`, or
any `gold_cot_features` row has `information_available_ts < report_date`.

**Assertion failing against the current (pre-fix) table, then passing:**

```
BEFORE (04:00/05:00 stamps):
  options info_ts >= session close: 19390 violating rows   <- FAILS

AFTER (rebuild):
  options info_ts >= session close: 0 violating rows       <- PASSES
  cot info_ts >= report_date:      0 violating rows
```

**New tests in `tests/gold/test_pit_leakage.py`** (run locally on DuckDB):
- `test_options_availability_not_derived_from_event_ts` — guard: no `MAX(event_ts)` / `last_ts` info_ts.
- `test_options_sql_has_named_buffer_constant` — guard: named buffer constant.
- `test_silver_quotes_is_stale_uses_snapshot_time` — guard: snapshot-time `is_stale`.
- `test_options_availability_invariant_catches_start_of_day_stamp` — the invariant flags 04:00, passes 20:30.
- `test_model_features_asof_join_excludes_same_day_options_intraday` — AS-OF join: a 15:00 UTC prediction gets the **prior** day's options (pcr 1.5) with the fix; the negative control (04:00 stamp) leaks the same-day options (pcr 2.0).

---

## 5. Rebuild — row counts unchanged, availability corrected ✅

Re-ran `gold_options_features` and `gold_model_features` through their existing
MERGE paths (serverless Spark, `databricks-connect`):

```
gold_options_features   19390 -> 19390  (delta 0)
gold_model_features     43345 -> 43345  (delta 0)
```

Post-rebuild `information_available_ts` time-of-day: **20:30 (12,859 summer) /
21:30 (6,531 winter)** — exactly the expected ~20:30/~21:30 UTC. A downstream
sanity check confirms `gold_model_features` has 0 joined options rows with
`information_available_ts > prediction_ts` (no look-ahead).

---

## Non-blocking notes

- `gold_model_features.prediction_ts` is end-of-day (last minute bar of the
  market spine), so in the *current* table the AS-OF join always saw same-day
  options regardless. The fix still matters: it corrects the stored
  `information_available_ts` for any intraday consumer, and the 343+145 rows at
  20:00/21:00 UTC prediction time now correctly fall back to the prior day's
  options rather than same-day.
- The `to_utc_timestamp` vs `convert_timezone` deviation is documented in the SQL
  header and here; use `convert_timezone` for any future DST-aware conversions.
- Pre-existing `.agents/dispatch.sh` mode change (100755→100644) was left
  unstaged — not part of this round.

## Checks run

- `python3 -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → **8 passed**
- `python3 -m py_compile pipelines/run_silver_gold.py` → OK
- `DATABRICKS_PROFILE=evangohsg python3 pipelines/run_silver_gold.py --check` → 8/8 PIT/DQ clean + availability invariant 0/0
- Rebuild script → counts 19390/43345, invariant 0, tod 20:30/21:30 (pasted above)
- Pre-fix invariant → 19390 violating rows (pasted above)
