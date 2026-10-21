# Evidence — volatility & risk-sizing layer (Phase 1)

**Status: SUCCESS.** Code commit `967cb3d2628b092d97df5ca340bef5ebf2555e8b`;
this evidence file is added in a follow-up docs-only commit. The final
`BUILD DONE` line reports the resulting HEAD.

| | |
| --- | --- |
| Branch | `feat/vol-risk-layer` |
| Base | `origin/main` = `0dc5b1c3e4598a6ea2c3b22f28cac7125da4b123` |
| Worktree | `/home/jianj/code/qp1-vol` |
| Python | 3.12.3 |
| Polars | 1.44.2 (`ewm_*`/`rolling_*` support `min_samples` and `ddof`) |
| pytest | 9.1.1 |

## 1. What was built

Polars-only library plus a seeded synthetic experiment. numpy is used only by
the synthetic GARCH generator and for small scalar test data; there is no
data-frame bridge. No source file under `risk/` or `tests/risk/` imports a
dataframe library other than Polars (the guard test enforces this); the
backtester imports scalar cost helpers from `strategies.cost_model`, which the
request explicitly permits.

| file | purpose |
| --- | --- |
| `risk/estimators.py` | EWMA var/cov/corr (`adjust=False`, `bias=False` == ddof 1), rolling 5/20/60 vol (`ddof=1`), overnight gap vs intraday vol, past-only 252-session percentile with a 252-observation guard, vol floor. |
| `risk/sizing.py` | one `size(signal_or_pair, estimates, params)` entry point; `equal_dollar`, `inverse_vol`, `covariance_aware`, `vol_target`; hedge ratio, floored spread variance, vol/gross scale, non-finite -> 0 weights. |
| `risk/pair_backtest.py` | `backtest_vol_pair`; close-t signal -> open-t+1 fill, open-to-open P&L; flat 5/10/15 bps per side or ADV mode; borrow only on short held notional; `CostParams` reused; Polars cost expression parity-tested against `cost_per_trade`. |
| `risk/compare.py` | the same signal through every sizer with identical execution; OOS Sharpe, realized vs target vol, max drawdown, gross/net exposure, turnover, borrow, at each cost level. |
| `risk/regimes.py` | past-only percentile regime labels `low`/`mid`/`high`; short history -> `unknown`. |
| `risk/config.py`, `risk/config.yaml` | typed config; every parameter read from YAML. |
| `risk/synthetic.py`, `risk/run_compare.py` | seeded correlated GARCH-like two-asset panel; writes `risk/results/p1_compare.md`. |
| `risk/README.md` | usage, assumptions, limitations (one page). |
| `tests/risk/` | 21 production-logic tests, including the dataframe guard. |

### Execution mapping (important correction)

`w_exec[t] = w[t-1]` is the book established at the open of row `t`. Row `t`'s
open-to-open return spans `open[t-1] -> open[t]`, so it is earned by
`w_held[t] = w_exec[t-1] = w[t-2]`, not by the book filled at `open[t]`.
The backtester therefore applies two explicit shifts: the signal shift (fill at
the next open) and the holding shift (P&L starts one interval later). Using
`w_exec[t]` for the return would let a weight decided at close `t-1` earn the
gap into its own fill price. `tests/risk/test_backtest.py::test_weight_decided_at_close_cannot_earn_the_next_open_gap`
fails if the execution shift is removed (mutation (a)).

## 2. Acceptance

All commands were run in the foreground through one LF Bash script per round
under `.agents/`, invoked only as
`wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-vol/.agents/run-vol-p1-<n>.sh`.
No inline `wsl ... -c`, no PowerShell/CMD wrapper, no repository command through
a Windows host. `python` is not installed in this WSL; `python3` is the
interpreter CI-equivalent commands were run with.

### 2a. Risk suite

```
$ python3 -m pytest tests/risk -q
.....................                                                    [100%]
21 passed in 4.96s
```

### 2b. Lint

CI (`.github/workflows/ci.yml`) has no ruff/lint step. As the repository's
available lint gate:

```
$ python3 -m ruff check risk tests/risk
All checks passed!
```

### 2c. Forbidden dataframe bridge

`rg` is not installed in this WSL, so the equivalent command was used:

```
$ grep -rn --exclude-dir=__pycache__ --exclude='*.pyc' "pan""das" risk tests/risk
risk/README.md:87:* No pandas bridge: everything under `risk/` and `tests/risk/` is Polars
tests/risk/test_no_pandas.py:41:    assert "test_no_pandas.py" not in names
```

The only matches are the README prose that documents the absence and the guard
test's own literal filename (the guard scans `.py` sources and excludes itself).
No `risk/*.py` or other `tests/risk/*.py` contains the bridge.

### 2d. CI-parity suite, normal environment

```
$ python3 -m pytest -q -m "not spark and not lakebase and not databricks"
1 failed, 2963 passed, 64 skipped, 24 deselected, 607 warnings in 360.98s
FAILED tests/rag/test_zz_isolation.py::test_databricks_connect_not_polluted
```

Triage: this test passes alone (`1 passed in 1.92s`) and the same full-suite
failure occurs with `--ignore=tests/risk`:

```
$ python3 -m pytest -q -m "not spark and not lakebase and not databricks" --ignore=tests/risk
1 failed, 2942 passed, 64 skipped, 24 deselected, 607 warnings in 328.45s
FAILED tests/rag/test_zz_isolation.py::test_databricks_connect_not_polluted
```

It is a pre-existing order/environment-sensitive isolation test (pyspark
4.4.0.dev0 is installed locally); it is independent of this additive diff.

### 2e. CI-parity suite, pyspark blocked (AGENTS standing rule)

Stub `pyspark/__init__.py` raising `ModuleNotFoundError("No module named
'pyspark'")` in `/tmp/vol-p1-stub`, first on `PYTHONPATH`, outside the repo:

```
$ PYTHONPATH=/tmp/vol-p1-stub python3 -m pytest -q -m "not spark and not lakebase and not databricks"
2954 passed, 74 skipped, 24 deselected, 607 warnings in 338.05s
```

0 failures. The 21 new tests are the difference between the two normal-run
totals (2963 with them, 2942 without).

Full-suite provenance: the run above was on code SHA
`5d2f86579e34b0e119f62fc1de2a9d5f9fdcaf98`. The final code SHA
`967cb3d2628b092d97df5ca340bef5ebf2555e8b` differs only in documentation and
test assertions:

```
$ git diff --stat 5d2f865... HEAD
 risk/README.md                |  3 +--
 tests/risk/test_estimators.py | 15 +++++++++++++++
 2 files changed, 16 insertions(+), 2 deletions(-)
```

No production Python module, config value or result report changed. The risk
suite and every mutation proof were re-run on the final SHA.

### 2f. Line endings and worktree

`file` reports UTF-8/ASCII text for every new source and the experiment report;
`grep -rIlU $'\r' risk tests/risk` found no CRLF. After the code commit,
`git status --porcelain` is empty. No push, no merge, no deploy, no shared-table
write.

## 3. Mutation proofs (isolated `git archive` copies)

Each case starts from a **fresh** `git archive 967cb3d` copy under
`/tmp/vol-p1-mut2/<case>` (no worktree copy), applies one exact mutation, runs
the named test, then runs the same test in the untouched archive as control.

| # | mutation | named test | mutated | control |
| --- | --- | --- | --- | --- |
| a | remove the execution `shift(1)` in `risk/pair_backtest.py` | `test_weight_decided_at_close_cannot_earn_the_next_open_gap` | **FAILED** `assert 0.050000000000000044 == 0.0` | 1 passed |
| b | remove the variance floor (scalar + expression) in `risk/sizing.py` | `test_floors_and_non_finite_inputs_keep_weights_finite` | **FAILED** `assert 0.0 >= 0.0025` | 1 passed |
| c | EWMA reads the next bar's return (`returns.shift(-1)`) in `risk/estimators.py` | `test_future_perturbation_leaves_estimators_and_regime_unchanged` | **FAILED** estimator frames differ | 1 passed |
| d | remove the `max_gross` cap in `risk/sizing.py` | `test_gross_never_exceeds_max_gross_when_scale_wants_more` | **FAILED** `assert 9.249662155992514 <= 2.000000001` | 1 passed |
| e | charge borrow on the long leg in `risk/pair_backtest.py` | `test_borrow_only_on_short_notional` | **FAILED** long-only borrow `-0.0003500000000000001` vs `0.0` | 1 passed |

Raw outputs were captured in the session log outside the repository (not
committed); the excerpts above are verbatim. The baseline archive suite was
`21 passed in 5.52s`.

## 4. Experiment deliverable

`risk/results/p1_compare.md`, generated by `python3 -m risk.run_compare`
(seed `20261022`, 1500 synthetic sessions, 50% OOS, `momentum_z` reference
signal). It states plainly that the data are synthetic and proves plumbing, not
alpha.

```
| variant | cost_bps | oos_sharpe | ann_return | realized_vol_gross | target_vol | vol_gap | max_drawdown | gross_exposure_avg | net_exposure_avg | turnover_avg | borrow_cost_total | net_pnl_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| equal_dollar | 5.0000 | -0.4870 | -0.0618 | 0.1171 | 0.1000 | 0.0171 | -0.2736 | 1.0000 | 0.0000 | 0.1893 | 0.0094 | -0.1696 |
| equal_dollar | 10.0000 | -0.6906 | -0.0840 | 0.1171 | 0.1000 | 0.0171 | -0.2951 | 1.0000 | 0.0000 | 0.1893 | 0.0094 | -0.2406 |
| equal_dollar | 15.0000 | -0.8926 | -0.1056 | 0.1171 | 0.1000 | 0.0171 | -0.3219 | 1.0000 | 0.0000 | 0.1893 | 0.0094 | -0.3116 |
| inverse_vol | 5.0000 | -0.6737 | -0.0712 | 0.1016 | 0.1000 | 0.0016 | -0.2811 | 1.0000 | 0.0129 | 0.2053 | 0.0093 | -0.2045 |
| inverse_vol | 10.0000 | -0.9223 | -0.0950 | 0.1016 | 0.1000 | 0.0016 | -0.3089 | 1.0000 | 0.0129 | 0.2053 | 0.0093 | -0.2814 |
| inverse_vol | 15.0000 | -1.1658 | -0.1182 | 0.1016 | 0.1000 | 0.0016 | -0.3374 | 1.0000 | 0.0129 | 0.2053 | 0.0093 | -0.3584 |
| covariance_aware | 5.0000 | -0.6370 | -0.0772 | 0.1150 | 0.1000 | 0.0150 | -0.3027 | 1.1632 | 0.0040 | 0.2737 | 0.0109 | -0.2191 |
| covariance_aware | 10.0000 | -0.9289 | -0.1086 | 0.1150 | 0.1000 | 0.0150 | -0.3351 | 1.1632 | 0.0040 | 0.2737 | 0.0109 | -0.3217 |
| covariance_aware | 15.0000 | -1.2141 | -0.1389 | 0.1150 | 0.1000 | 0.0150 | -0.3721 | 1.1632 | 0.0040 | 0.2737 | 0.0109 | -0.4244 |
| vol_target | 5.0000 | -0.8962 | -0.0835 | 0.0922 | 0.1000 | 0.0078 | -0.2936 | 0.8627 | 0.0030 | 0.2440 | 0.0081 | -0.2467 |
| vol_target | 10.0000 | -1.2239 | -0.1113 | 0.0922 | 0.1000 | 0.0078 | -0.3301 | 0.8627 | 0.0030 | 0.2440 | 0.0081 | -0.3382 |
| vol_target | 15.0000 | -1.5479 | -0.1382 | 0.0922 | 0.1000 | 0.0078 | -0.3660 | 0.8627 | 0.0030 | 0.2440 | 0.0081 | -0.4297 |
```

At the baseline 10 bps, the vol-target variant's realized gross vol is 0.0922
(gap 0.0078) versus equal-dollar 0.1171 (gap 0.0171). The dispersion test
`test_vol_target_tracks_target_better_than_equal_dollar` asserts this
relationship on a seeded panel. This is a plumbing result only.

## 5. Test coverage map (required cases)

1. Worked example: `test_worked_example_hedge_ratio_and_spread_vol` -> `h ==
   0.625`, spread vol ~= 0.158 via production `hedge_ratio`/`spread_volatility`/`size`.
2. No look-ahead: `test_past_weights_unchanged_by_future_perturbation` perturbs
   rows `>= cut` and requires decisions strictly before `cut` to be
   byte-identical; `test_future_perturbation_leaves_estimators_and_regime_unchanged`
   perturbs strictly future rows and requires estimators, percentile, regime
   and weights at `<= cut` to be byte-identical. A decision dated `cut` uses
   `cut`'s own close, which is contemporaneous information, not a future leak;
   the strict-future test covers the `<= t` assertion literally.
3. Execution lag: `test_execution_lag_shock_cannot_affect_earlier_pnl` and
   `test_weight_decided_at_close_cannot_earn_the_next_open_gap`.
4. Floors/caps: `test_floors_and_non_finite_inputs_keep_weights_finite`,
   `test_gross_never_exceeds_max_gross_when_scale_wants_more`,
   `test_vol_target_clips_alpha_and_respects_gross_cap`.
5. Overnight vs intraday: `test_overnight_and_intraday_vol_use_different_return_definitions`
   (10x construction asserted at 8-12x).
6. Costs: `test_doubling_cost_lowers_net_pnl_when_turnover_positive`,
   `test_zero_turnover_has_zero_cost`, `test_borrow_only_on_short_notional`,
   `test_polars_cost_expression_matches_scalar_cost_per_trade`.
7. Compare harness: `test_vol_target_tracks_target_better_than_equal_dollar`;
   `test_comparison_covers_every_sizer_with_finite_metrics`.
Plus `test_no_pandas.py` source guard and the ddof pin test
`test_rolling_vol_pins_sample_ddof_one_and_annualization`.

## 6. Known issues from the request — handled

* Adjusted prices: the layer consumes price columns and derives returns only
  from ratios of adjusted levels; adjusted levels are never features. Stated in
  `risk/README.md`.
* Log close-to-close estimates vs open-to-open P&L: deliberate, documented in
  `risk/README.md`; the execution mapping uses two shifts so P&L starts after
  the fill.
* `turnover = sum |delta w|` ignores intraday weight drift: documented in the
  README and in the result-report footer; costs are a lower bound under drift.
* No hardcoded MAGS/SOXX: pair columns and all parameters are config fields.
* Short history: 252-session percentile with `percentile_min_history: 252`
  returns null and regime `unknown`; tested on a 10-row frame.

## 7. Non-goals (verified)

No Spark, Databricks call, live data, deploy, execution/api/agent/db edits, no
changes to `.github/**`, `requirements*.txt`, `databricks.yml`, `silver/`,
`gold/`, `sql/`, or `strategies/**`. No push to `main`; no merge. No credentials
or secrets were read, printed, or committed. No model training, table rebuild,
or shared-signal write.

## 8. Worktree hygiene note

A second, concurrent `dsbuild` attempt in this same worktree wrote an untracked
dataframe-library-based sketch (`risk/params.py`, a different `risk/regimes.py`,
and three test files) plus a failure note. Those files were not part of this
implementation, conflicted with the request's Polars-only policy, and were
removed before the commit. The committed `risk/` subtree is the Polars
implementation described above (subtree hash
`e90b30985654170f4c76e556abbf533c9a701e68`), and the worktree is clean.
