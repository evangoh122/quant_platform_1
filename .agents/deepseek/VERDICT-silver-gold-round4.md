# VERDICT: silver-gold round 4 (look-ahead leak) — DeepSeek
**Status:** APPROVED
**Round:** 4

Fixes the three blocking findings Codex raised on PR #8 (whole-day `session_high`
look-ahead, a disconnected PIT test, and a COT percentile that ranked by date
rather than value) plus the full `silver/`/`gold/` window-function audit the
request demanded. Committed as `f97257e`.

---

## 1. Session high/low look-ahead — FIXED ✅

`gold/01_gold_ohlcv_features.sql:28-29` now computes session high/low with a
trailing frame:

```sql
MAX(high) OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_high,
MIN(low)  OVER (PARTITION BY symbol, DATE(event_ts) ORDER BY event_ts
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_low
```

A 09:31 bar can no longer see the 15:59 high. Verified on the rebuilt table
(§5): on all **43,345** `(symbol, day)` first bars, `session_high == high`:

```
first_bars=43345  session_high_eq_own_high=43345
SPY 2022-01-03 first_bar high=476.92  trailing_session_high=476.92  old_whole_day_high=478.09
```

---

## 2. Window-function audit (every `OVER` in `silver/` and `gold/`)

| File:line | Window | Verdict |
| :-- | :-- | :-- |
| `silver/01_silver_ohlcv.sql:62` | `ROW_NUMBER() OVER (PARTITION BY symbol,event_ts,timespan ORDER BY ingest_ts DESC, source)` | SAFE — dedup preference, not a time feature |
| `silver/02_silver_ohlcv_quarantine.sql` | (none) | SAFE |
| `silver/03_silver_options_quotes.sql:41` | `MAX(participant_ts) OVER (PARTITION BY underlying)` | SAFE* — partition-wide MAX, but only feeds `is_stale`, a snapshot-internal quality flag with no `information_available_ts` and not propagated to any gold feature |
| `silver/04_silver_options_trades.sql` | (none) | SAFE |
| `silver/05_silver_sec_sections.sql:26` | `ROW_NUMBER() OVER (PARTITION BY accession_number,filing_section ORDER BY chunk_id)` | SAFE — chunk ordering within a filing |
| `silver/06_silver_sec_entities.sql:63,115` | `ROW_NUMBER() OVER (PARTITION BY accession_number ORDER BY cik)` | SAFE — dedup pick-one-per-accession |
| `silver/07_silver_cot_positions.sql` | (none) | SAFE |
| `gold/01_gold_ohlcv_features.sql:24-27` | `LAG(close, 1/5/15/30) OVER (... ORDER BY event_ts)` | SAFE — LAG is backward by construction |
| `gold/01_gold_ohlcv_features.sql:28-29` | `MAX/MIN OVER (... ORDER BY event_ts ROWS UNBOUNDED PRECEDING..CURRENT)` | **FIXED** (was whole-day leak) |
| `gold/01_gold_ohlcv_features.sql:69-74` | `STDDEV/AVG OVER w5/w14/w15/w20/w30` (ROWS `n-1` PRECEDING..CURRENT) | SAFE — trailing frames |
| `gold/02_gold_options_features.sql:60-63` | `AVG/STDDEV(total_volume) OVER w` (ROWS 19 PRECEDING..CURRENT) | SAFE — trailing |
| `gold/02_gold_options_features.sql:80,88,96,122` | `ROW_NUMBER() OVER (PARTITION BY symbol,d ORDER BY ...)` | SAFE — snapshot-internal ranking |
| `gold/02_gold_options_features.sql:109-110` | `MIN/MAX(expiry) OVER (PARTITION BY symbol,d)` | SAFE* — partition-wide over a single snapshot day (term structure), not a trailing time series |
| `gold/04_gold_cot_features.sql:44` | `LAG(lev_money_net) OVER (PARTITION BY mapped_asset ORDER BY report_date)` | SAFE — backward |
| `gold/04_gold_cot_features.sql:52-66` | `AVG/STDDEV OVER (... ROWS 51 PRECEDING..CURRENT)` | **FIXED** (was expanding history) |
| `gold/04_gold_cot_features.sql:33` | `ROW_NUMBER() OVER (PARTITION BY mapped_asset ORDER BY report_date)` | SAFE — ordering key for the trailing self-join |
| `gold/04_gold_cot_features.sql:78-80` | self-join `b.rn BETWEEN a.rn-51 AND a.rn` | SAFE — trailing 52-report window |
| `gold/05_gold_model_features.sql:40,51,62` | `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY information_available_ts DESC)` | SAFE — picks latest AS-OF; join already filters `info_ts <= prediction_ts` |
| `gold/gold_sec_features.py` | (none — Python, sorts by `accepted_ts`, prior-filing only) | SAFE |

\* `silver/03:41` and `gold/02:109-110` are partition-wide aggregates with no
`ORDER BY`, so they match the audit's syntactic pattern, but they are not PIT
leaks: both operate over a single-day snapshot (there is no "future" within the
partition), neither is exposed with an availability timestamp, and neither is
propagated into a gold feature. Left as-is, documented here.

No `FOLLOWING`, no `LEAD`, and no full-history mean/stddev used as a z-score
baseline remains anywhere in `silver/` or `gold/`.

---

## 3. COT percentile / z-score — FIXED ✅

`gold/04_gold_cot_features.sql` rewritten (see §Checks):

- **Percentile** is now a true trailing 52-report **value** percentile
  (`percent_rank` semantics: `# trailing values strictly below / (n-1)`), not a
  `RANK()` by `report_date`. Spark ranking functions cannot take a bounded
  `ROWS` frame, so the trailing window is materialised with a self-join on
  `ROW_NUMBER()` (`b.rn BETWEEN a.rn-51 AND a.rn`).
- **z-score** now uses a bounded `ROWS BETWEEN 51 PRECEDING AND CURRENT ROW`
  mean/stddev, not the expanding history.
- First 51 reports per `mapped_asset` have a partial window → percentile/z-score
  NULL (same convention as the options `volume_anomaly_zscore`'s first ~19 days).

Independent recomputation (Python over the `equity_index` series) matches the
stored values exactly: **0 mismatches across 243 rows**, `pctile ∈ [0,1]`,
`zscore ∈ [-2.93, 2.25]`, row 0 (`2022-01-04`) NULL as expected.

---

## 4. PIT test now exercises the real build ✅

`tests/gold/test_pit_leakage.py` no longer tests an in-memory comparator the
build never calls. It is a **future-invariance** test that extracts the real
feature SQL from `gold/01_gold_ohlcv_features.sql` verbatim and runs it on a
local DuckDB DataFrame (window expressions copied byte-for-byte; only the Delta
table FQN, the `universe`/date filters, and `current_timestamp()`→`now()` are
adapted; `processed_ts` is excluded from comparison). Three tests:

- `test_production_sql_uses_trailing_session_window` — guards the build file
  itself carries the trailing (not whole-day) frame.
- `test_future_invariance_holds_for_fixed_sql` — the fixed SQL is invariant.
- `test_old_session_high_window_is_detected_as_leak` — negative control: the old
  whole-day window **must** break invariance (a test that can't fail on the old
  SQL is worthless).

Both outputs (old fails / new passes):

```
=== FIXED (trailing window) ===
rows with feature_ts <= cut compared; mismatches = 0

=== OLD (whole-day window) ===
rows with feature_ts <= cut compared; mismatches = 4
   ('AAA', 2026-01-05 09:30) dist_session_high truncated=-0.5 full=-0.75
   ('AAA', 2026-01-05 10:30) dist_session_high truncated=0.0  full=-0.5
   ('BBB', 2026-01-05 09:30) dist_session_high truncated=-0.5 full=-0.75
   ('BBB', 2026-01-05 10:30) dist_session_high truncated=0.0  full=-0.5
```

`python3 -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → **3 passed**.
Runs on DuckDB, so it needs no Databricks workspace (no `@pytest.mark.databricks`).

---

## 5. Rebuild — row counts unchanged, values corrected ✅

Re-ran `gold_ohlcv_features`, `gold_cot_features`, `gold_model_features`
through their existing MERGE paths (serverless Spark, `databricks-connect`).
Counts unchanged (MERGE updates matched rows in place):

```
gold_ohlcv_features  23377478 -> 23377478  (delta 0)
gold_cot_features        1464 ->     1464  (delta 0)
gold_model_features     43345 ->    43345  (delta 0)
```

`session_high` on each day's first bar equals that bar's own high: 43,345/43,345
(§1). COT recomputation check: 0 mismatches (§3).

---

## Non-blocking notes

- **Pre-existing universe defect (round 3, still open, out of scope):**
  `config/universe.yaml:50` `- ON` is YAML-parsed to boolean `True`, so the
  universe carries `TRUE` instead of `ON` (ON Semiconductor). Not fixed here —
  it touches the silver layer and `config/`, both outside this request.
- `processed_ts` is intentionally rewritten on MERGE-matched rows (unchanged
  convention from rounds 2–3); it is excluded from the future-invariance
  comparison for that reason.
- The DuckDB test is a faithful but adapted execution of the production SELECT
  (table FQN / filters / `current_timestamp()` substituted). It proves the
  window logic is PIT-safe; the §5 Databricks run proves the real SQL executes
  and yields the corrected values at full scale.

## Checks run

- `python3 -m pytest tests/gold/test_pit_leakage.py --noconftest -v` → 3 passed
- `python3 /tmp/round4_demo.py` → FIXED 0 mismatches / OLD 4 mismatches (pasted above)
- `python3 /tmp/round4_rebuild.py` → before/after counts 23377478/1464/43345, deltas 0
- `python3 /tmp/round4_verify.py` → first-bar session_high==high 43345/43345; SPY sample shows old whole-day high ≠ trailing high
- `python3 /tmp/round4_cot_check.py` → 243 rows recomputed, 0 mismatches; pctile∈[0,1], first report NULL
