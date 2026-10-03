# BUILD: strategy robustness round 6, Codex review (MiMo)

Read `.agents/codex/VERDICT-strategy-robustness.md`. Each fix needs a test that FAILS on the current
HEAD (prove it in /tmp).

1. **[Blocking] PCA loadings depend on day-t availability.** At `strategies/residual_reversion.py:~310`,
   `day_t.notna()` decides which symbols the loading matrix is fitted on.
   - Fit the factors and loadings on the `[t-window, t-1]` window only. Symbol eligibility for the FIT
     must use only that window, e.g. ≥ `min_obs` valid observations in it.
   - Apply day t only when projecting and computing the residual. A symbol with NaN on day t simply
     gets no residual that day.
   - Test: setting one day-t return to NaN (and separately to a huge value) leaves the day-t loadings
     matrix IDENTICAL in shape and values for every other symbol.
2. **[Blocking] Make the unused-`compute_*` guard real.** Add an AST-based test. Parse
   `strategies/run_residual_reversion.py`; every name imported from `strategies.robustness` must be
   CALLED somewhere reachable from `main` or `_run_variant`. Either wire in the 7 Codex listed
   (`compute_capacity`, `compute_exposures`, `compute_fold_metrics`, `compute_margin_bps`,
   `run_cost_stress`, `run_parameter_stress`, `run_universe_stress`) where the report needs them, or
   delete the dead imports and duplicate code paths. Don't keep both. Mutation: adding an unused
   `compute_*` import fails the test.
3. **[Spec] Validate the PCA component count** to [10, 15] in config validation and in
   `compute_pca_residuals`. Raise `ValueError` outside the range. Fix the test that allows 0.

Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Leave no scratch
files. Commit with a descriptive message. Write `.agents/mimo/VERDICT-strategy-robustness-round6.md`.
