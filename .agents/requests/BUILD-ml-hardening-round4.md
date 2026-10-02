# BUILD-REQUEST: ml-hardening — ROUND 4 (don't neutralise market-wide features)

**Branch:** `slice/ml-hardening` · **Builder:** MiMo
Round 3 is verified: neutralisation now runs on 365/370 timestamps, skips are
counted and warned, and 66 of 68 features have post-neutralisation correlation
with beta of exactly 0. Keep all of it.

## The defect (measured by the coordinator)

The two remaining non-zero correlations are both COT features:

```
neutralisation after: cot_lev_money_zscore vs beta corr = -0.0509
neutralisation after: cot_crowding_score   vs beta corr =  0.0225
```

Every COT column has **exactly one distinct value per `prediction_ts`** across
all 18 symbols (`make_synthetic_matrix`): COT is a market-wide regime signal.
Regressing a cross-sectionally constant column on industry dummies leaves a
residual of ~0, so neutralisation **erases** it; the reported correlations are
floating-point noise on a zeroed column.

Consequence: in the A/B/C/D ablation, arm **D (+COT) has its distinguishing
features zeroed**, so the D-vs-C comparison is meaningless. The RSP/SPY breadth
indicator planned in `docs/QUANT_STRATEGIES.md` is also market-wide and would
suffer the same fate.

## Fix

1. In `neutralize_features`, **detect market-wide columns automatically**: a
   feature whose values are constant across symbols within (almost) every
   timestamp. Exclude them from residualisation and pass them through unchanged.
2. Log which columns were excluded and why, alongside the neutralised/skipped counts.
3. Optionally allow an explicit `market_wide_cols` override, but the automatic
   detection must work without it.
4. Exclude non-numeric and timestamp columns (`cot_information_available_ts`,
   `cot_regime_label`) from the feature list given to neutralisation if they are
   currently being passed in.

## Tests

- A cross-sectionally constant feature survives neutralisation **unchanged**
  (bitwise or within 1e-12), and appears in the excluded-columns log.
- The real runner: COT features are non-zero after neutralisation, and arm D's
  feature matrix differs from arm C's in the COT columns.

Paste `python3 -m pytest tests/ml -q -m "not spark and not databricks"` and,
from one real `python3 -m ml.run_ablation` run, the excluded-columns log line.
Do **not** commit `ml/results/ablation_abcd.md` changes produced by test runs
unless that artifact is the intended output of this round.

Do not touch `silver/`, `gold/`, `agent/`, `db/`, `api/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`. **Commit your work.** Write `.agents/mimo/VERDICT-ml-hardening-round4.md`.
