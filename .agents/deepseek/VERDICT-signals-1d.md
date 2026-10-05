===VERDICT START===
# VERDICT: signals-1d — DeepSeek (checker)

**Status:** APPROVED
**Round:** 1

Checker read-only. All mutations applied to a disposable `git archive HEAD` copy
under `/tmp/qp1-mut/`; no worktree file edited. Shipped code == `HEAD`
(`1f35f2f`), which carries the three named commits `9488d19`, `c38bfd0`,
`7b2564a` verbatim for `ml/`, `scripts/`, `tests/`.

## The five CHECK questions

### 1. Three named mutations — each must fail a test

Re-run against the SHIPPED `daily_close_labels` (not inline re-implementations;
the D6 tests at `tests/ml/test_baseline_labels.py:544-626` call the shipped
`daily_close_labels` directly — `grep` confirms no `_forward_labels_plain_shift`
-style tautological helpers exist):

| Mutation | Edit (`ml/baseline_labels.py`) | Result |
|---|---|---|
| `close_ts <= prediction_ts` → `trade_date <= prediction_ts.date()` | `:145-159` merge_asof keyed on `to_datetime(trade_date)` / `prediction_ts.dt.date` | **3 failed** (`test_mutation_lookahead_guard_trade_date_vs_close_ts`, `test_daily_close_after_prediction_ts_never_used_as_d`, `test_daily_snapshot_before_close_uses_previous_day`) |
| drop `max_gap` check | `:174` → `valid = ... & (gap > 0)` | **2 failed** (`test_mutation_drop_max_gap_check`, `test_daily_gap_exceeds_max_gap_days_is_nan`) |
| label from N+1 | `:132-134` `shift(-1)` → `shift(-2)` | **1 failed** (`test_mutation_label_from_n_plus_1`) |

The "same as signals-pit round 1 N1" concern does **not** apply: the D6 tests
exercise the shipped function; they do not re-implement the buggy logic inline.

### 2. Look-ahead — can close_D ever have `close_ts > prediction_ts`?

No. D selection is `pd.merge_asof(..., right_on="_cts"=close_ts, direction="backward")`
at `ml/baseline_labels.py:150-159`, which structurally enforces `close_ts <=
prediction_ts`. Probe (EST `20:59` / EDT `19:59` close_ts, snapshots at `00:30`
UTC next-day and at `14:00` UTC pre-close) confirmed `close_D.close_ts <=
prediction_ts` in every row. For US equities the regular-session close is always
`16:00 ET` = `19:59/20:59 UTC`, i.e. the same UTC date as its ET `trade_date`,
so there is no UTC-midnight/DST crossing for the close itself; the ET `trade_date`
is used only for grouping/next-day lookup, never for the `<=` predicate.

### 3. The tz warning — correctness risk today?

`ml/baseline_labels.py:121` initialises `out["label_ts"] = pd.NaT` (tz-naive
`datetime64[ns]`); `:182-183` then writes tz-aware `datetime64[ns, UTC]` values.
pandas (2.2.1) upcasts the column to `object` and preserves the tz — probe shows
`label_ts.dtype == object`, value `Timestamp('... +0000', tz='UTC')`, and
`purged_split`/`refit_rows` `label_ts <= cut` comparisons return correct bools.
**Not a value-correctness bug today**, but a latent defect: the `FutureWarning`
becomes a hard error in a future pandas, and `object` dtype is less type-safe
than a proper `datetime64[ns, UTC]` column. Fix is to initialise tz-aware
(e.g. `pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")`). Same
pattern pre-exists at `forward_labels:59,80`. Non-blocking (== signals-pit N5).

### 4. Warehouse SQL

`scripts/publish_baseline_signals.py:53-65`. Table names `T` and `SILVER` are
module constants; the only interpolated value is the `symbol IN (...)` list from
`df.symbol.unique()` (DB-derived from `gold_model_features`, **not** user input),
so "no user values" holds. Regular-session filter is correct: `is_regular_session
= true`, `timespan = 'minute'`, `max_by(close, event_ts)` = close of the last
regular-session minute, `max(event_ts)` = its `close_ts` (last minute ≈
`19:59/20:59` UTC per DST), grouped/dated via
`to_date(from_utc_timestamp(event_ts, 'America/New_York'))`. `max_by(close,…)`
and `max(event_ts)` share the same `event_ts`, so close and close_ts are
consistent. Note: the symbol list is string-interpolated (not parameterized);
safe here only because it is DB-derived — prefer a `JOIN gold_model_features` or
binding for robustness.

### 5. All-UP output — bug or honest weak model?

Honest weak model, not a bug. AUC `0.533` ≈ random, which rules out leakage
(leakage would inflate AUC). All-UP follows mechanically: `direction = "UP" if
prob >= 0.5` (`ml/score.py:68`) and logistic regression with near-zero feature
coefficients plus a slightly positive base-rate drift (intercept) yields all
probabilities just above 0.5 (`0.518–0.542`). Fixture logic in
`tests/ml/test_baseline_labels.py` produces both `0` and `1` labels — no
imbalance bug. The script does **not** print label balance (train/test fraction
of `label==1`), so "all UP" is not self-diagnosable from its stdout; recommend
adding `print(f"label balance train {(tr.label==1).mean():.3f} test
{(te.label==1).mean():.3f}")`.

## Blocking findings

None.

## Non-blocking notes

- [`ml/baseline_labels.py:121,183`] tz-naive `label_ts` initialisation → FutureWarning
  + `object` dtype (see item 3). Latent future-pandas breakage; should fix.
- [`scripts/publish_baseline_signals.py:53`] `symbols_sql` f-string interpolation
  of DB-derived symbols; not user input but not parameterized. Prefer a JOIN.
- [`scripts/publish_baseline_signals.py:66-67`] `close_ts`/`prediction_ts` are
  `pd.to_datetime(...)` without an explicit `.dt.tz_localize("UTC")`; correctness
  depends on the Databricks SDK returning consistent tz-aware timestamps for both
  `gold_model_features.prediction_ts` and `max(event_ts)`. Works today (prior live
  run), but an explicit UTC localize would remove the implicit assumption.
- [`scripts/publish_baseline_signals.py:69-90`] No label-balance diagnostic
  printed (see item 5).
- MiMo's "15 existing + 12 new" test count is slightly off: actual breakdown is
  14 pre-existing (`forward_labels` 11 + `purged_split` 2 + `refit_rows` 1) and
  13 `daily_close_labels`. Total 27 is correct.

## Checks run

- `python3 -m pytest tests/ml/test_baseline_labels.py -q` → **27 passed** (matches MiMo's 27)
- mutation *look-ahead `trade_date <= prediction_ts.date()`* → **3 failed**
- mutation *drop max_gap check* → **2 failed**
- mutation *label from N+1 (`shift(-2)`)* → **1 failed**
- `grep` for inline re-implementations in `tests/ml/test_baseline_labels.py` → **none**
- DST/midnight look-ahead probe (EST/EDT close_ts, pre-close & post-midnight snapshots) → **close_D always `<= prediction_ts`**
- tz dtype probe (`label_ts` dtype/value after `daily_close_labels`) → **object dtype, tz-preserved, comparisons correct**
- `git log` → `9488d19`, `c38bfd0`, `7b2564a` all ancestors of `HEAD` (`1f35f2f`)
===VERDICT END===
