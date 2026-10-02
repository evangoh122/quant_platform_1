# BUILD-REQUEST: ml-hardening — ROUND 3 (neutralisation still a no-op)

**Branch:** `slice/ml-hardening` · **Builder:** MiMo
Round 2's label selector and DSR fixes are verified working — keep them.

## The defect (measured by the coordinator)

Neutralisation now raises if `market_beta`/`industry` are absent — good — but in
the real runner it performs **zero** regressions:

```
regressions expected=4070 performed=0 (0%)  symbols/timestamp=6  industries=5  design_cols=7
```

`ml/features.py` skips a timestamp when `valid.sum() <= design.shape[1]`. The
design is intercept + beta + 5 industry dummies = 7 columns, and the default run
has 6 symbols per timestamp, so **every** timestamp is skipped silently. The
"after" log then averages un-neutralised data: max |corr with beta| after was
0.098, *higher* than typical "before" values. Unit tests pass only because they
use a larger cross-section than the real runner.

This is the same silent-no-op defect as round 1, one level down.

## Fix

1. **Count and surface skips.** `neutralize_features` must count timestamps
   neutralised vs skipped and return/log both. If **any** timestamp is skipped,
   log a WARNING with the counts; if **all** are skipped, **raise**.
2. **Fix the design.** Full industry dummies plus an intercept are collinear
   (dummy trap). Drop the intercept, or drop one dummy level. Then the minimum
   cross-section is beta + K industries, not +1 more.
3. **Make the synthetic runner meaningful.** The default synthetic universe must
   have comfortably more symbols per timestamp than design columns (for example
   `n_symbols >= 3 * (1 + n_industries)`). Raise the default `--n-symbols`, or
   reduce synthetic industries — and state which and why.
4. **Report only neutralised timestamps** in the "after" correlation, and print
   the neutralised/skipped counts next to it.

## Tests

- The real runner path (not a hand-built frame) neutralises > 0 timestamps, and
  post-neutralisation mean |corr(feature, beta)| < 1e-6 on neutralised timestamps.
- An underdetermined cross-section (symbols ≤ design columns) raises when it is
  the only kind present, and warns with counts when mixed.

Paste: `python3 -m pytest tests/ml -q -m "not spark and not databricks"` and the
neutralised/skipped counts from one real `python3 -m ml.run_ablation` run.

Do not touch `silver/`, `gold/`, `agent/`, `db/`, `api/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`. **Commit your work.** Write `.agents/mimo/VERDICT-ml-hardening-round3.md`.
