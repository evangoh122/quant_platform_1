===VERDICT START===
# VERDICT: strategy-robustness-check4 — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 10 (robustness round-4 re-check)

Re-checked commit `40c2ea6` (MiMo round 4) at HEAD `6266a8b` on
`slice/strategy-robustness`. Read-only; all scratch under `/tmp`. Nothing
committed or pushed. Working tree clean.

## Blocking findings

1. **[strategies/run_residual_reversion.py:575,587-588 vs 760] Per-fold drop-top-3 now
   identifies the top-3 P&L contributors from *residual* returns, not the returns the
   backtest actually trades.**
   Round 4 changed `_run_variant` to store `"residual_returns": sig.get("residual")`
   (line 760, correct for rank IC). But the per-fold drop-top-3 loop in `main()` still
   reads `ret_full = hold_vr["residual_returns"]` (line 575) and computes
   `pnl_sym = (w_full.shift(1).fillna(0.0) * ret_full).sum()` (lines 587-588) to pick the
   three largest contributors. The strategy's realized P&L, however, is
   `lagged_weight × tradeable_return` — `run_one(...)` passes `sig["returns"]` (raw
   close-to-close returns, line 722), never `sig["residual"]`. The two frames are not the
   same quantity (`compute_residuals` returns the OLS/PCA regression residual, not the raw
   return). Round 4 was asked only to make the OOS comparison net-vs-net; the silent
   semantic change to the *selection* step was not requested and regresses it.
   → Concrete failure: a synthetic probe (market-dominated panel, distinct per-symbol
   betas) shows the top-3 by actual P&L is `{S11, S07, S10}` while the top-3 by residual
   P&L is `{S03, S08, S05}` — different names. The report's "OOS Sharpe (drop3)" is
   therefore computed on the wrong trimmed universe, and `all_dropped_symbols` names the
   wrong symbols. Note the registry's `top_pnl_removal` variant (`remove_top_pnl_contributors`,
   robustness.py:212) correctly uses raw `returns`, which makes the divergence concrete.

2. **[strategies/robustness.py:836-843] The Rank IC table reports neither the t-stat
   method nor the effective n.**
   Round-4 item 2 requires "Report which one, plus the effective n." `compute_rank_ic`
   returns `effective_n` (robustness.py:455) and the t-stat is Newey-West HAC lag H-1,
   but `render_robustness_report` renders only columns `mean IC | IC t-stat | n | sign |
   hit rate`, printing the overlapping `ric['n']` and never `ric['effective_n']`, and
   never stating "Newey-West HAC, lag=H-1".
   → Concrete failure: a reader sees `n ≈ 500` with no signal that consecutive IC values
   are H-overlapping (effective n ≈ n/H), undermining the "honest t-stat" the round
   explicitly asked for.

## Answers to the round-4 re-check list

| # | Item | Result |
|---|------|--------|
| 1 | Rank IC target is the forward residual sum | **PASS** — `build_signals` exposes `res["residual"]` (run_residual_reversion.py:252); `_run_variant` stores it as `residual_returns` (:760); `compute_rank_ic` target is `rolling(H).sum().shift(-H)` = residual returns t+1..t+H (robustness.py:416), no day-t leakage. |
| 2 | t-stat HAC or non-overlapping | **PARTIAL** — HAC SE (Bartlett, lag H-1) is correct and `effective_n` is computed (robustness.py:373-396,441-445); but the report omits the method and `effective_n` (finding 2). |
| 3 | Drop-top-3 re-runs full backtest → net vs net | **PARTIAL** — OOS comparison is now genuinely net-vs-net (re-runs `build_signals`+`run_one` with costs/neutralisation/ADV cap on the trimmed eligible set, run_residual_reversion.py:598-616); but the top-3 are *selected* from residual returns (finding 1). |
| 4 | Sector exposure reported as max |net| | **PASS** — `compute_exposures` returns per-sector `max(abs(per-date net))` and overall `max_abs_sector_exposure` (robustness.py:283-310); report renders `max |sector net| (name)` and `(overall)` (robustness.py:785-789). |

No other newly-miscomputed quantity found: the residual-IC target, HAC t-stat, and
max-|sector-net| are computed on the correct quantities; the only wrong-quantity defect
in this round is the drop-top-3 selection (finding 1).

## Non-blocking notes

- **[strategies/run_residual_reversion.py:617-618]** `except Exception: pass` silently
  falls back to `oos_full` if the trimmed backtest fails, which would render
  `drop3 == full` (a misleading "no change") instead of surfacing the error.
- **[strategies/robustness.py:206-212]** `remove_top_pnl_contributors` (the
  `top_pnl_removal` registry variant) still sums `lagged_weight × return` gross of cost
  allocation despite the docstring's "allocated costs" — pre-existing, out of round-4
  scope.
- `pca_components` remains unvalidated to [10, 15] (carried from rounds 7/8).

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
158 passed, 34 warnings in 92.93s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types = None)
158 passed, 34 warnings in 94.88s

# probe: build_signals returns != residual; top-3 by raw vs residual differ
returns equals residual? -> False
top-3 by ACTUAL returns : ['S11','S07','S10']
top-3 by RESIDUAL returns: ['S03','S08','S05']
```
===VERDICT END===
