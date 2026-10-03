# BUILD-REQUEST: silver-gold — ROUND 3 (options sourcing fix)

**Branch:** `slice/silver-gold` (continue from `e1d9c85`)
**Scope:** narrow. Round 2 succeeded — **do not rewrite it.**

## Round 2 worked

47,012,381 rows now exist where there were zero. `silver_ohlcv` 23.4M across 39
symbols, `gold_ohlcv_features` 23.4M, `silver_sec_entities` 49,687,
`silver_cot_positions` 15,427, `gold_model_features` 14,958. Good work. The MVP
universe filter was applied correctly (39 symbols).

**Leave all of that alone.** Three targeted problems follow.

## Problem 1 — options features used the wrong source table (the big one)

`gold_options_features` has **12 rows on a single date**. Cause:

| Table | Rows | Distinct dates | Underlyings |
| :-- | --: | --: | --: |
| `bronze_options_quotes` *(you used this)* | 61,882 | **1** (2026-09-02 only) | 12 |
| `bronze_options_day` *(the real history)* | **146,117,971** | **503** (2024-09-04..2026-09-04) | 7,770 |

`bronze_options_quotes` is a one-day snapshot. `bronze_options_day` is the
146M-row daily options history and is **the largest table in the lakehouse** —
it is the project's Volume evidence and it is currently unused.

### What to do

Re-source `gold_options_features` from `bronze_options_day`, and be honest about
the split, because the two sources carry different columns:

**Available from `bronze_options_day` across 503 dates** — build these:
- `put_volume`, `call_volume`, `put_call_ratio` (from `right` + `volume`)
- `volume_anomaly_zscore` (per-underlying rolling z-score of total option volume)
- option-volume-to-equity-volume ratio
- term/strike structure of *volume* (e.g. share of volume in near expiries,
  share out-of-the-money) using `expiry`, `strike`, `right`, `event_date`
- `trade_count`-based flow intensity

**NOT available from `bronze_options_day`** — it has no IV or greeks:
- `iv_atm`, `iv_25d_put`, `iv_25d_call`, `iv_skew`, `iv_term_slope`,
  `net_delta_exposure`, `oi_concentration`

Those exist **only** in `bronze_options_quotes`, for **one date**. Therefore:
- Populate the IV/greek columns for that single date only, from the snapshot.
- Leave them NULL for all other dates. **Do not interpolate, forward-fill or
  synthesise them** — a forward-filled IV across 503 days would be fabricated
  data and would silently corrupt any model trained on it.
- State this limitation explicitly in your verdict and in a comment in the
  transform.

Also build `silver_options_day` if a silver staging layer helps, but check the
target schema first — if no such table exists, do not invent one; write
`gold_options_features` directly and say so.

**Expect this to go from 12 rows to hundreds of thousands.** Report the real count.

## Problem 2 — `gold_sec_features` has only 128 rows

`silver_sec_sections` has 10,720 rows and `silver_sec_entities` 49,687, yet
`gold_sec_features` produced 128. Investigate and report the cause with numbers.
Likely candidates: an inner join dropping most filings, a per-filing aggregation
when per-symbol-per-date was intended, or the sentiment step silently failing on
most chunks.

If 128 is genuinely correct (e.g. one row per filing event and there are only
128 qualifying events), prove it with a count query and say so. Do not inflate it.

## Problem 3 — `gold_model_features` covers 12 symbols, not 39

`silver_ohlcv` has 39 symbols but `gold_model_features` has 12. That is probably
an inner join against the single-date options features (problem 1) or against
the 18-ticker SEC universe.

After fixing problem 1, rebuild `gold_model_features` and ensure:
- The PIT join is a **LEFT** join from the market-feature spine outward, so a
  symbol is not dropped merely for lacking options or SEC coverage.
- Missing optional features are NULL, not imputed.
- `information_available_ts` discipline is preserved (`NOT NULL` in schema).
- Report the final symbol count and row count.

## Still required

- Schemas must match `docs/DATA_SCHEMAS.md` exactly — targets already exist.
- Re-running must not duplicate rows. Paste before/after counts.
- The PIT leakage test must still fail on an injected leaking row.
- Universe filter from `config/universe.yaml` stays applied.

## Do not touch

`db/`, `agent/` (Lane A), `ml/`, `tests/ml/` (ML lane), `api/`, `frontend/`
(app lane), `conftest.py`, `pytest.ini`, `requirements*.txt`, `.agents/`.

## Acceptance criteria

1. `gold_options_features` sourced from `bronze_options_day`, with a real row
   count in the hundreds of thousands. Paste `SELECT COUNT(*)` and
   `COUNT(DISTINCT feature_ts)`.
2. IV/greek columns NULL outside the single snapshot date — **not** filled.
   Paste a query proving they are NULL elsewhere.
3. `gold_sec_features` cause diagnosed with numbers; fixed or justified.
4. `gold_model_features` symbol count reported; left-join semantics confirmed.
5. Idempotency shown.
6. **Commit your work.**

## When finished

`.agents/deepseek/VERDICT-silver-gold-round3.md`, leading with the row-count
table before and after.
