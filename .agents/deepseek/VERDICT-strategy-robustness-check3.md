===VERDICT START===
# VERDICT: strategy-robustness-check3 — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 9 (robustness round-3 re-check)

Re-checked commit `499b502` (MiMo round 3) at HEAD `1a6fcbf` on
`slice/strategy-robustness`. Read-only; all scratch under `/tmp`. Nothing
committed or pushed. Working tree clean at end (only the pre-existing
coordinator-owned `.agents/dispatch.sh` modification remained).

## Blocking findings

1. **[strategies/run_residual_reversion.py:251, 725, 545-548] Rank IC is computed against raw total returns, not residual returns.**
   `build_signals` returns `"returns": tradeable_returns` (raw close-to-close
   returns masked to the PIT universe, line 251) and never exposes
   `res["residual"]` — the value `compute_residuals` /
   `compute_pca_residuals` actually produce (`strategies/residual_reversion.py:263`
   OLS, `:388` PCA). `_run_variant` stores it under the misleading name
   `"residual_returns": sig.get("returns")` (line 725), and `main()` feeds that
   into `compute_rank_ic(s_score, residual_returns=…)` (lines 545-548).
   → Concrete failure: the "## Rank IC" table reports the Spearman correlation of
   the residual s-score against **total** return. Total return is dominated by the
   market/industry factor return that the s-score is orthogonal to by construction,
   so the reported IC is not the "s-score[t] vs residual return t+1..t+H" measure
   the BUILD spec (change 3) and round-3 BUILD item 1 both mandate. A probe
   confirms `build_signals` returns only `{beta_mkt, industry, market, positions,
   returns, s_score}` — no `residual` key — and that `sig["returns"]` is
   element-wise identical to the raw returns frame.

2. **[strategies/robustness.py:403] The Rank IC t-stat is not honest.**
   `t_stat = mean / (std / np.sqrt(len(ic_series)))` treats the daily IC series as
   independent. The forward H=5-day target windows overlap by 4 days between
   consecutive dates, so the IC series is strongly autocorrelated and the effective
   sample is ~n/H. Round-3 BUILD item 1 explicitly requires "Newey-West or the
   non-overlapping-sample count"; neither is implemented.
   → Concrete failure: `sqrt(n)` with n≈full date count inflates the reported IC
   t-stat by ~sqrt(H) (~2.2× at H=5), overstating the significance.

3. **[strategies/run_residual_reversion.py:579 vs 584] Per-fold drop-top-3 compares net to gross.**
   `oos_full = net.reindex(common_val).dropna()` is the **net** (after-cost) series
   (line 579), while `oos_drop3 = (per_sym_val.drop(columns=top3, errors="ignore").sum(axis=1))`
   is `lagged_weight × raw_return` summed — a **gross** P&L with no cost allocation
   and no rebalance/neutralisation (line 584). The two `_sharpe(...)` values are
   therefore not like-for-like.
   → Concrete failure: the "OOS Sharpe (full)" vs "OOS Sharpe (drop3)" columns
   compare a net Sharpe to a gross Sharpe, systematically overstating the drop-3
   robustness. The train-window selection itself is correct (see item 4 below).

## Answers to the round-3 re-check list

| # | Item | Result |
|---|------|--------|
| 1 | Rank IC alignment, no overlap leakage, honest t-stat | **FAIL** — target is raw (finding 1), t-stat naive (finding 2). Target shift itself is correct: `future_ret = …shift(-H)` (`robustness.py:380`) uses only t+1..t+H, no signal leakage. |
| 2 | Capacity numbers sane vs ADV | **PASS** — formula `participation_cap·ADV/|Δw|` is correct and sane; caveats in notes. |
| 3 | Exposures use real betas and taxonomy | **PARTIAL** — real `beta_mkt` and repo-taxonomy `industry` now flow in (`run_residual_reversion.py:726-727` → `robustness.py:733-735`); but industry summary is mean **signed net** exposure, not the requested "max |sector net| per sector" (note). |
| 4 | Drop-top uses only train-window P&L | **PARTIAL** — top-3 chosen from `w.shift(1)·ret` over `train_net.index` only (train window) **PASS**; but OOS comparison is gross-vs-net (finding 3). |
| 5 | Guard test FAILS on `0e972e0` | **PASS** — reproduced: `0e972e0`'s `render_robustness_report` lacks `rank_ic_results`/`drop_top3_results` kwargs → all 6 guard tests fail with `TypeError`. |

No other report section is a bare placeholder: Rank IC, capacity, exposures and
per-fold drop-top now all emit computed numbers (previously stubbed). The remaining
defects are that several of those numbers are computed on the wrong quantity
(findings 1-3), not that they are uncomputed.

## Non-blocking notes

- **[strategies/robustness.py:283-297]** Industry exposure summarises `np.mean` of
  the per-date **signed** net weight, not "max |sector net| per sector" (round-3
  item 3). Functionally present, but the summary statistic does not match the ask.
- **[strategies/robustness.py:763, 770-783]** Capacity: `compute_capacity`'s
  `book_capital` argument is dead (never referenced); the report hardcodes
  `participation_cap = 0.01` (line 770) instead of reading
  `cost_model.adv_participation_cap`; the "book size binding >X% trades" label is
  misleading — it prints the X-th percentile of the per-trade capacity distribution
  (≈X% of trades bind, not ">X%"); `pct_bound` (line 782) is computed but never
  rendered. The inline loop (771-783) duplicates `compute_capacity`.
- **[tests/strategies/test_robustness_round3.py]** The guard test fails on `0e972e0`
  only via `TypeError` on the new kwargs, not a behavioral assertion, and it does
  **not** implement the round-3 mandate "every `compute_*` function imported by the
  runner is actually called" / "no unused imports from `strategies.robustness`".
  The runner still imports `run_cost_stress`, `run_universe_stress`,
  `run_parameter_stress` (`run_residual_reversion.py:509-511`) which are never used
  (MiMo's own note). MiMo's verdict overstates this guard.
- **[strategies/run_residual_reversion.py:537]** Rank IC uses the single configured
  `rank_ic_horizon_days` (5); if "for H in the hold candidates" (round-3 item 1)
  was meant literally as H∈{3,5,10}, only H=5 is computed.
- `pca_components` is still not range-validated to [10, 15] (carried from rounds
  7/8).

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
150 passed, 34 warnings in 87.19s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types = None)
150 passed, 34 warnings in 82.22s

# guard test against pre-round-3 HEAD (0e972e0, via /tmp worktree)
$ python3 -m pytest -q -p no:cacheprovider tests/strategies/test_robustness_round3.py
6 failed  (TypeError: render_robustness_report() got an unexpected keyword argument 'rank_ic_results')

# build_signals exposes no residual key; sig["returns"] == raw returns (probe)
keys: ['beta_mkt','industry','market','positions','returns','s_score']
```
===VERDICT END===
