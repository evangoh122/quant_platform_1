# VERDICT: strategy-residual-reversion-round2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Non-blocking notes
- The end-to-end run confirms all four fixes land correctly. R2 numbers are
  worse than R1 on the unconditional baseline (net Sharpe -0.331 vs -0.318),
  which is expected: the ADV cap prevents oversized positions from earning
  returns they could never realise, and the universe fix removes look-ahead
  membership that was inflating the tradable set.
- Gated ablation: net Sharpe +0.346 but fails at 2× costs (-0.183). DSR 0.003.
  The caveat is now explicit in the results file.
- Walk-forward OOS Sharpe degraded to -0.619 (from -0.378 in R1). The stricter
  universe and ADV cap reduce the exploitable opportunity set.
- The `cap_weight_changes_by_adv` function is vectorised (numpy) — no
  per-symbol Python loop in the hot path.
- All modified files have LF line endings.

## Checks run
- `python -m pytest tests/strategies/ -v` → 24 passed
- `python strategies/run_residual_reversion.py` → completed, wrote r2.md
- `python -c "line endings check"` → all LF (0 CRLF on modified files)
- `git diff --stat` → 7 files, +262/-21