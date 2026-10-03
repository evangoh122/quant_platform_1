===VERDICT START===
# VERDICT: strategy-robustness-check5 — DeepSeek
**Status:** APPROVED
**Round:** 11 (robustness round-5 re-check)

Re-checked commit `cc2f9e0` (MiMo round 5) at HEAD `9206ca4` on
`slice/strategy-robustness`. Read-only; all scratch under `/tmp`. Nothing
committed or pushed. Working tree clean.

## Blocking findings (both check4 findings now resolved)

### Check4 finding 1 — per-fold drop-top-3 by realised P&L — FIXED

Proof:
- `_run_variant` now stores the two quantities under **distinct keys**
  (`strategies/run_residual_reversion.py:761-762`):
  `"trade_returns": sig.get("returns")` (raw close-to-close tradeable returns,
  the exact frame `run_one` trades at line 468/477) and
  `"residual_returns": sig.get("residual")` (OLS/PCA regression residual, used
  only for rank IC).
- The per-fold selection loop reads `ret_full = hold_vr["trade_returns"]`
  (`run_residual_reversion.py:574`) and computes
  `pnl_sym = (w_full.shift(1).fillna(0.0) * ret_full).sum()` over the train
  window (`:588-589`). This is `lagged_weight × tradeable_return`, the same
  basis `remove_top_pnl_contributors` uses (`robustness.py:212`). Both paths now
  share one realised-P&L basis; the residual frame is no longer fed into name
  selection.
- Rank IC now reads `vr.get("residual_returns")` (`run_residual_reversion.py:554`),
  so the two consumers can no longer be confused.

### Check4 finding 2 — Rank IC disclosure — FIXED

Proof:
- `render_robustness_report` now emits
  `_t-stat method: Newey-West HAC (Bartlett kernel, lag = H-1)._`
  (`robustness.py:837`) and a table header with an `eff. n` column (`:839`),
  populated from `ric.get("effective_n", ric["n"])` (`:842-845`).
- `compute_rank_ic` still returns `effective_n = n // H` and the HAC t-stat
  (`robustness.py:442-445`). A direct probe rendered the section with the
  method note and `| ols_mkt_ind | -0.0500 | -3.20 | 90 | 18 | ...` — the
  effective n is present next to n.

## Final full pass — every report quantity

Each row: computed, on the right quantity, without look-ahead, like-for-like.

| Report quantity | Verdict |
|---|---|
| Factor-model net/IS/OOS Sharpe, OOS/IS, DSR | **PASS** — `_sharpe(net)` on `vr["net"]`; IS/OOS from the chronological 80/20 split; DSR uses `n_trials=len(registry)` |
| Cost stress (2×/3×) net Sharpe | **PASS** — `compute_costs(..., cost_multiplier=cost_mult)` scales commission/spread/slippage/**borrow** exactly once (`backtest.py:161-170,192`); `net = gross - costs["total"]`, no double application |
| Universe stress (200/500) | **PASS** — re-screens via `screen_universe(panel, n=us)` on the same dense-grid path as `fetch_data` |
| Parameter perturbation (±20%) | **PASS** — one param perturbed per variant; window rounded/clamped |
| Top-3 P&L contributor removal (registry variant) | **PASS** — `remove_top_pnl_contributors` selects by `lagged_weight × returns` (raw), drops names by zeroing them, rebuilds signals |
| Per-fold drop-top-3 OOS (full vs drop3) | **PASS** — top-3 by realised P&L on the **train window only**; OOS comparison re-runs the actual backtest (neutralise, ADV cap, costs) on the trimmed universe → net-vs-net |
| Walk-forward folds (per-fold Sharpe) | **PASS** — `compute_fold_metrics(baseline_vr["net"], splits)` on purged/embargoed validation folds |
| Exposures (dollar, beta, sector) | **PASS** — dollar `sum(w)/gross`; beta `sum(w·β)/gross`; sector `max |net|` per sector plus overall max |
| Turnover / capacity / margin | **PASS** — one-way turnover mean; capacity percentiles on the ADV-capped open leg; margin bps from net/turnover |
| Rank IC | **PASS** — target = forward H-day **residual** sum (`rolling(H).sum().shift(-H)` → t+1..t+H, no day-t leakage); HAC t-stat lag H-1; `n` and `eff. n` disclosed |
| Gate summary | **PASS** — five gates evaluated per variant on the correct metrics; OOS/IS ratio gate on `oos_sharpe/is_sharpe` |
| Honest trial count | **PASS** — registry dedups by fingerprint; baseline deduplicated once; 72 unique variants all counted; rank IC and per-fold drop-3 derive from already-counted baseline variants (no extra uncounted trials) |

No remaining "looks computed but isn't" quantity found in this pass. The round-8
merge did not regress the cost path (costs still charge on actual executed
notional, `backtest.py:213-216`) nor the dense-grid screen in `fetch_data`
(`run_residual_reversion.py:138`).

## Non-blocking notes

- **[strategies/run_residual_reversion.py:618]** `except Exception: pass`
  silently falls back to `oos_full` when the trimmed backtest fails, which would
  render `drop3 == full` (a misleading "no change") instead of surfacing the
  error — carried from round 4.
- **[strategies/robustness.py:212]** `remove_top_pnl_contributors` still sums
  `lagged_weight × return` gross of cost allocation, despite the docstring's
  "allocated costs" — pre-existing, out of round-5 scope.
- **Test-count wording.** The round-5 BUILD asked "each new test must FAIL on
  the current HEAD"; 6 of 7 do. The 7th
  (`test_top3_by_realised_differs_from_residual_in_market_dominated_panel`) is a
  synthetic-probe sanity check that validates the probe setup itself, so it
  passes on any HEAD by construction. Not a code-guard test — no action needed.
- `pca_components` remains unvalidated to [10, 15] (carried from rounds 7/8).

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
165 passed, 34 warnings in 89.02s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types = None)
165 passed, 34 warnings in 91.06s

# probe: round-5 tests on pre-round-5 HEAD (git worktree at 04ec167)
6 failed, 1 passed (the passing test is the probe-validation test, see notes)

# probe: rendered Rank IC section shows method note + eff. n column with values
| factor model | mean IC | IC t-stat | n | eff. n | sign | hit rate |
| ols_mkt_ind | -0.0500 | -3.20 | 90 | 18 | negative (expected under mean reversion) | 0.65 |
```
===VERDICT END===
