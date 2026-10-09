# VERDICT: performance-ratios-hardening — MiMo

**Status:** APPROVED
**Round:** 1

Builder evidence for `BUILD-performance-ratios-hardening.md` (MiMo lane). Per
PROTOCOL.md a builder may not approve its own work as the sole verdict — this
file is one input; the gate still requires the DeepSeek, Codex and Claude
verdicts. Base commit `6d851c7`; build request commit `6886bf1`; this build
lands as `8bf6d6d` on `feat/performance-ratios` (no push, nothing on main).

## Blocking findings
(none)

## Fixes applied

### 1. Sample sufficiency gate — `strategies/report.py::performance_metrics`
- New parameter `min_observations_for_ratios: int = 252`.
- Always returns `observation_count` (int) and `sample_state` (`"ok"` /
  `"insufficient_sample"`), including the empty-input path.
- When `observation_count < min_observations_for_ratios`, `sharpe_ratio`,
  `sortino_ratio`, `calmar_ratio` are NaN; `total_return`, `cagr`,
  `annualized_volatility`, `max_drawdown`, `win_rate`, `profit_factor`,
  `payoff_ratio`, `trade_count`, `average_win`, `average_loss` stay numeric.
- Docstring states the reason: SE of an annualized Sharpe grows like
  `sqrt(252 / T)`.

### 2. Sharpe uncertainty — `strategies/report.py`
- When `sample_state == "ok"`: `sharpe_ci_95_low` / `sharpe_ci_95_high` around
  the annualized Sharpe with iid large-sample SE
  `sqrt((1 + 0.5 * SR_p**2) / T) * sqrt(periods_per_year)` (`SR_p` = per-period
  Sharpe, `T` = observation count), half-width `z_{0.975} * SE`
  (`z_{0.975}` from stdlib `statistics.NormalDist().inv_cdf(0.975)`; no new
  dependency).
- Key `sharpe_ci_method = "iid_normal_approx"` always returned (it names the
  method used whenever the CI is computable); the numeric bounds are NaN when
  the sample is insufficient.
- Docstring documents that it assumes iid returns and **understates
  uncertainty under autocorrelation** (volatility clustering, overlapping
  labels, stale marks).

### 3. Annualization transparency
- `performance_metrics` echoes `periods_per_year` in its output; docstring
  warns the factor must match the label horizon (daily labels -> 252).
- `ml/evaluate.py::build_backtest` returns the `periods_per_year` it used,
  plus `observation_count` / `sample_state` and the three Sharpe-CI keys from
  the report; docstring warns the default of 3276 assumes 30-minute bars and
  must not be used with daily labels.

### 4. Quarantine `ml/evaluate.py::deflated_sharpe_ratio` — NOT rewritten
- Docstring now leads with `RESEARCH-ONLY — KNOWN-UNRELIABLE` and the two
  known defects exactly as specified (annualized Sharpe fed into per-period
  PSR variance / `sqrt(n-1)` terms; unit-variance expected maximum with no
  trial-SR variance).
- Emits `warnings.warn(..., UserWarning)` on every call (`stacklevel=2`).
  Logic untouched.
- Guard test `tests/ml/test_evaluate.py::test_no_api_or_frontend_imports_ml_evaluate_or_deflated_sharpe`:
  walks real source files under `api/` and `frontend/`, parses `.py` with
  `ast` (Import/ImportFrom rooted at `ml`) and text-scans every
  `.py/.ts/.tsx/.js/.jsx/.mjs/.cjs` file for `deflated_sharpe_ratio`,
  `ml.evaluate`, `ml/evaluate`. Currently zero hits.

### 5. Turnover convention
- Computation sites: `strategies/backtest.py` (weights) and
  `ml/evaluate.py::build_backtest` (per-row position flips). Actual convention
  is now stated at both sites and pinned by test:
  **one-way turnover = `sum_s |Δw| / 2 / target_gross`** (`|Δw|` is two-way
  traded notional, `/2` keeps one side); the inline `run_backtest` math was
  extracted verbatim into `strategies/backtest.py::one_way_turnover` so the
  production path is directly testable. `ml/evaluate.py`'s per-row form is
  `|Δposition| / 2` (a long<->short flip = one two-sided trade = 1.0).
- `strategies/config.yaml` comment corrected: the old `true = divide by 2`
  contradicted both the code and the docs; it now states one-way =
  `sum|Δw|/2` (WQ default, what `one_way_turnover` computes) vs two-way =
  `sum|Δw|`.

## Test shape (all mandated tests present; production functions called; expected values are hand-computed literals shown in comments)

- `test_ratio_literals_on_252_observation_fixture` — alternating
  `+0.01/-0.005` x 126 (T=252); Sharpe `5.280993172584953`, Sortino
  `11.224972160321826`, Calmar `172.5900614423098` within 1e-9; full
  arithmetic in the header comment block of `tests/strategies/test_report.py`.
- `test_short_sample_gates_ratios_but_keeps_other_metrics_numeric` — T=100:
  three ratios NaN, `sample_state == "insufficient_sample"`,
  `observation_count == 100`, other metrics finite.
- `test_sharpe_uses_sample_std_ddof_one` — ddof=1 literal vs ddof=0 literal
  `5.291502622129182` (differs by ~1e-2 >> tolerance).
- `test_sortino_downside_deviation_is_rms_over_all_periods` — pins
  `sqrt(126*0.000025/252)` over ALL 252 periods vs negatives-only RMS `0.005`
  (`7.937253933193772`).
- `test_calmar_uses_cagr_not_annualized_arithmetic_return` — CAGR-based
  `172.59...` vs arithmetic-annualized `126.0`.
- `test_sharpe_ci_95_matches_iid_normal_approx_half_width` — T=252:
  `low < Sharpe < high`, half-width literal `2.0134612777914342`
  (= `1.9599639845400536 * 1.0272950389258988`) within 1e-12.
- `test_build_backtest_one_portfolio_return_per_timestamp` — 2 symbols x 20
  shared timestamps: `observation_count == 20 == nunique(prediction_ts)`.
- `test_one_way_turnover_long_flat_short` — weights `[1, 0, -1]`:
  turnover `[0.5, 0.5, 0.5]` (and `[0.25, 0.25, 0.25]` at `target_gross=2`).
- `test_build_backtest_turnover_is_one_way_flip_fraction` — positions
  `[+1, +1, -1]`: `turnover == 1/3`.
- `test_deflated_sharpe_ratio_warns_research_only` — `pytest.warns(UserWarning,
  match="RESEARCH-ONLY")`.
- Guard test per item 4 (ast + text scan over `api/`, `frontend/`).

## Mutation transcripts (each in an isolated `git archive` copy of `8bf6d6d4abe5d0b606895f635e2a7e67517c88b3`, never a `cp -r` working repo)

Command per case (from the archive root; mutator asserts each edit applies
exactly once before the run):

```
git -C /home/jianj/code/qp1-ratios archive 8bf6d6d4... | tar -x -C /tmp/mimo-mut/M<n>
<apply one textual mutation>
python3 -m pytest tests/strategies tests/ml -q
```

| M | Mutation (applied) | pytest exit | Failed tests | Summary |
| --- | --- | --- | --- | --- |
| M1 | `excess.std(ddof=1)` -> `ddof=0` (`strategies/report.py`) | 1 | `test_ratio_literals_on_252_observation_fixture`, `test_sharpe_uses_sample_std_ddof_one`, `test_sharpe_ci_95_matches_iid_normal_approx_half_width` | 3 failed, 136 passed |
| M2 | Sortino downside -> plain `std` of negatives (`strategies/report.py`) | 1 | `test_performance_ratios_have_expected_trade_math`, `test_ratio_literals_on_252_observation_fixture`, `test_sortino_downside_deviation_is_rms_over_all_periods` | 3 failed, 136 passed |
| M3 | Calmar `cagr/maxDD` -> `annualized_return/maxDD` (`strategies/report.py`) | 1 | `test_ratio_literals_on_252_observation_fixture`, `test_calmar_uses_cagr_not_annualized_arithmetic_return` | 2 failed, 137 passed |
| M4 | gate `observation_count >= min_observations_for_ratios` -> `>= 0` (`strategies/report.py`) | 1 | `test_empty_returns_are_reported_as_nan`, `test_short_sample_gates_ratios_but_keeps_other_metrics_numeric` | 2 failed, 137 passed |
| M5 | `df.groupby("prediction_ts", ...)["net_return"].mean()` -> `df["net_return"]` (`ml/evaluate.py`) | 1 | `test_build_backtest_one_portfolio_return_per_timestamp` | 1 failed, 138 passed |
| M6 | turnover divisor `/2.0` -> `/1.0` (`strategies/backtest.py::one_way_turnover` and `ml/evaluate.py`) | 1 | `test_one_way_turnover_long_flat_short` | 1 failed, 138 passed |
| M7 | delete `warnings.warn(...)` from `deflated_sharpe_ratio` (`ml/evaluate.py`) | 1 | `test_deflated_sharpe_ratio_warns_research_only` | 1 failed, 138 passed (77 warnings — the deleted warning is gone) |

All 7 mutations detected (every case exit=1 with the pinned test(s) failing).
Full per-case logs: `/tmp/mimo-mut/M*.log` (ephemeral runner output; the
summary above is the recorded transcript).

## Non-blocking notes

- `ml/evaluate.py`'s per-row turnover is `.clip(0.0, 1.0)`-ed and positions are
  always +-1, so `|Δposition| == 2` and **any** divisor >= 2 yields 1.0: a
  `2.0 -> 1.0` change at that site alone is unobservable by construction. The
  `1/3` literal in `test_build_backtest_turnover_is_one_way_flip_fraction`
  pins divisor *increases* (e.g. `2.0 -> 4.0` gives 1/6), and the `0.5`
  literal pins the `/2` at `strategies/backtest.py` both ways. M6 mutates both
  sites and is caught via the backtest test.
- `sharpe_ci_method` is always the string `"iid_normal_approx"`; only the
  numeric CI bounds are NaN-ed on insufficient samples (reading of "NaN CI
  keys").
- Existing `test_performance_ratios_have_expected_trade_math` (T=4 trade-math
  pin) now passes `min_observations_for_ratios=1` explicitly; its intent is
  unchanged and the gate itself is pinned by the new tests (incl. M4).
- Quarantine side effect (intended): `strategies/backtest.py::portfolio_metrics`,
  `strategies/run_residual_reversion.py` and `ml/evaluate.py::evaluate_predictions`
  call `deflated_sharpe_ratio`, so every call now warns. No test asserts on
  those warnings being absent; pre-existing tests still pass.
- `tests/ml/test_hardening.py` still exercises `deflated_sharpe_ratio` values;
  unchanged, now emits the quarantine warning (recorded in the run output).
- No changes under `api/`, `frontend/`, `silver/`, `gold/`; no new
  dependencies (`statistics.NormalDist` is stdlib); no deploy/Databricks/live
  data touched.

## Checks run

- `python3 -m pytest tests/strategies tests/ml -q` -> **139 passed, 96
  warnings in 76.21s** (baseline before this build: 128 passed).
- Mutation gauntlet M1-M7 (isolated `git archive` copies) -> 7/7 detected,
  transcripts above.
- `git status --short` on `feat/performance-ratios` -> clean after commit;
  nothing pushed to `main` (or anywhere).
