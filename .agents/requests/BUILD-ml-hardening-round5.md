# BUILD-REQUEST: ml-hardening — ROUND 5

**Branch:** `slice/ml-hardening` · **Builder:** MiMo · **Validators:** Claude, then Codex
Read `.agents/codex/VERDICT-ml-hardening-round4.md`. Codex confirmed DSR, trial count,
purge and embargo are correct — keep them. Three blocking findings:

## 1. `market_beta` uses the current bar (look-ahead)

`ml/synthetic_data.py:177-197`: `return` at `t` uses the close at `t`, the rolling
cov/var includes that return, and the beta is joined to the row at `t`. Minute bars in
this project are stamped at their **start** (coordinator verified on `bronze_ohlcv`: days
run 04:00→23:59), so a bar's close is not known at its own timestamp. **Shift the beta
by one bar** (`.shift(1)` within symbol) before joining, and apply the same rule to any
real-data beta path. Test: perturbing the return at `t` must not change beta at `t`.

## 2. Market-wide detection misclassifies sparse features

`ml/features.py:422-441`: threshold is 90% of timestamps, and `nunique(dropna=True) <= 1`
counts an all-NaN timestamp as "constant". A genuinely cross-sectional feature observed
on few timestamps is therefore classed market-wide and skips neutralisation.
Decide only over timestamps where the feature has **≥ 2 non-null values**; a column is
market-wide if it is constant on (almost) all of those. Columns with too few such
timestamps to decide must be **reported**, not silently classified.
Test: a sparse feature that varies cross-sectionally where observed is neutralised.

## 3. Market-wide classification is fitted on the full sample

`ml/train.py:252` calls `neutralize_features()` on the whole matrix before the
walk-forward loop, so validation-period timestamps influence the classification of
training rows. Make the classification **fold-local**: decide market-wide columns from
each fold's training timestamps only, then apply that decision to the fold's train and
validation rows. (The per-timestamp beta/industry regressions are already local and
may stay as they are.)
Test: the classification for fold k is unchanged when data after fold k's training
window is altered.

## Constraints

Do not touch `silver/`, `gold/`, `agent/`, `db/`, `api/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`. Do not commit `ml/results/ablation_abcd.md` changes from test runs.
Paste `python3 -m pytest tests/ml -q -m "not spark and not databricks"`.
**Commit your work.** Write `.agents/mimo/VERDICT-ml-hardening-round5.md`.
