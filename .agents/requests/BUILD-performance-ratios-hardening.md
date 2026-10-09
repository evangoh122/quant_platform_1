# Build: harden the Sharpe/Sortino/Calmar performance report

Builder: MiMo. Checker: DeepSeek. Then Codex final, Opus final, PR + CodeRabbit (see AGENTS.md / .agents/PROTOCOL.md).
Branch `feat/performance-ratios`, worktree /home/jianj/code/qp1-ratios, base commit 6d851c7 (rescued `strategies/report.py::performance_metrics`
and portfolio-level aggregation in `ml/evaluate.py::build_backtest`). Commit on this branch only. No deploy, no Databricks, no live data, no new dependencies.

## Why
Codex and Opus reviewed risk-adjusted-return handling. Agreed: these ratios are useful but unsafe on short samples, and parts of `ml/evaluate.py` are broken.
Do exactly the items below. Do NOT touch api/, frontend/, or silver/gold.

## Changes
1. **Sample sufficiency gate** in `strategies/report.py::performance_metrics`: add `min_observations_for_ratios: int = 252`. Always return `observation_count`
   and `sample_state` (`"ok"` or `"insufficient_sample"`). When observation_count < min, set `sharpe_ratio`, `sortino_ratio`, `calmar_ratio` to NaN
   (keep total_return, cagr, volatility, drawdown, win_rate, profit_factor, payoff_ratio numeric). Reason: SE of an annualized Sharpe is about sqrt(252/T).
2. **Uncertainty**: when sample_state is ok add `sharpe_ci_95_low` / `sharpe_ci_95_high` using the iid large-sample standard error of the *annualized* Sharpe
   `sqrt((1 + 0.5*SR_p^2)/T) * sqrt(periods_per_year)` where SR_p is the per-period Sharpe and T the observation count. Document in the docstring that it assumes iid
   returns and understates uncertainty under autocorrelation; add the key `sharpe_ci_method="iid_normal_approx"`. NaN CI keys when state is insufficient.
3. **Annualization transparency**: `performance_metrics` must echo `periods_per_year` in its output; `ml/evaluate.py::build_backtest` must include the
   `periods_per_year` it used in its returned dict. Add a docstring warning that the default must match the label horizon (daily labels -> 252).
4. **Quarantine `ml/evaluate.py::deflated_sharpe_ratio`**: it feeds an annualized Sharpe into per-period PSR variance/√(n−1) terms and compares against a
   unit-variance expected maximum with no trial-SR variance. Do NOT rewrite it. Mark it clearly RESEARCH-ONLY / known-unreliable in its docstring, make it emit a
   `warnings.warn(..., UserWarning)` when called, and add a guard test that nothing under `api/` or `frontend/` imports `ml.evaluate` or `deflated_sharpe_ratio`
   (parse real source files with `ast`/text scan over those directories).
5. **Turnover convention**: `strategies/config.yaml` (~line 113) comment says "true = divide by 2" while docs say one-way = Σ|Δw|/2. Find where turnover is computed
   (ml/evaluate.py and/or strategies/backtest.py), state the actual convention in one comment/docstring, and pin it with a hand-computed test: weights
   long→flat→short over 3 periods with exact expected turnover.

## Test shape (MANDATORY — call production functions; never copy their logic; expected values must be literals computed by hand, shown in comments)
- 252+ observation fixture with known mean/std (e.g. alternating +0.01/-0.005 repeated) → Sharpe/Sortino/Calmar literals within 1e-9; show the arithmetic in a comment.
- Short fixture (T=100) → three ratios NaN, `sample_state == "insufficient_sample"`, `observation_count == 100`, other metrics numeric.
- Sharpe uses ddof=1 (fixture where ddof differs from 0 beyond tolerance); Sortino downside deviation uses RMS of min(excess,0) over ALL periods.
- CI: with T=252 verify low<Sharpe<high and the exact half-width literal.
- Portfolio aggregation: `build_backtest` with 2 symbols at the same prediction_ts yields ONE portfolio return per timestamp (assert period count == distinct timestamps).
- DSR warns; guard test per item 4; turnover per item 5.

## Mutations that MUST make a test fail (run each in an isolated `git archive` copy, never git in a cp -r copy; record transcript in the evidence file)
M1 Sharpe std ddof=1→0. M2 Sortino downside via plain std of negatives. M3 Calmar uses annualized arithmetic return instead of CAGR. M4 remove the min-observations gate.
M5 remove the groupby(prediction_ts) aggregation in build_backtest. M6 change the turnover divisor. M7 delete the DSR warning.

## Acceptance
`python3 -m pytest tests/strategies tests/ml -q` passes. Write evidence to `.agents/mimo/VERDICT-performance-ratios-hardening.md`. Commit everything.
Finish with exactly one line:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/performance-ratios | evidence: .agents/mimo/VERDICT-performance-ratios-hardening.md`
