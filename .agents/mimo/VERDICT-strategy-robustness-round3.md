# VERDICT: strategy-robustness-round3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
None. All four blocking findings from DeepSeek check2 are resolved.

## Changes made

### 1. Rank IC is real (`strategies/robustness.py:404`, `strategies/run_residual_reversion.py:541-553`)
- `compute_rank_ic` called per factor model in the runner using `s_score` and `residual_returns` from `build_signals`.
- Report renders mean IC, t-stat, n, sign, and hit rate in a real table.
- Placeholder text ("Run with --rank-ic...") removed.
- `compute_rank_ic` now returns `hit_rate` (fraction of dates with negative IC).

### 2. Capacity is real (`strategies/robustness.py:740-770`)
- `compute_capacity` called on baseline weights with ADV data.
- Report shows p50 (median) and p5 capacity in dollars.
- Book-size binding threshold computed: for the 5th/10th/25th percentile of per-trade capacity constraints.
- `compute_capacity` now returns `p5_capacity` alongside `p10`/`p50`.

### 3. Exposures are complete (`strategies/robustness.py:726-733`)
- `beta_mkt` and `industry` from `build_signals` stored in variant results by `_run_variant`.
- `compute_exposures` called with real `beta` and `industry` parameters (no longer `None`).
- NaN beta/industry columns eliminated.

### 4. Drop-top-3 uses training-window P&L only (`strategies/run_residual_reversion.py:555-595`)
- Per walk-forward fold: top-3 names identified by P&L in that fold's TRAIN window only.
- Those names dropped; OOS Sharpe evaluated on the fold's VALIDATION window.
- Report shows per-fold table with dropped symbols and OOS Sharpe with/without them.
- One section per hold candidate (3, 5, 10).

### 5. Guard test (`tests/strategies/test_robustness_round3.py`)
- `test_report_has_no_placeholders`: renders report from synthetic data, asserts:
  - No "Run with", "TODO", "placeholder", "not available in variant results" in report.
  - Rank IC section has real mean IC, t-stat, n, hit rate.
  - Capacity section has p50 and p5 in dollars (not NaN).
  - Exposures section has real beta and industry data (not NaN).
  - Drop-top-3 section present with fold-level OOS Sharpe data.
  - Every required table has at least one numeric data row.
- Proved guard FAILS on pre-round-3 HEAD (old `render_robustness_report` rejects new kwargs).

## Checks run
- `python3 -m pytest -q tests/strategies` → 113 passed
- `python3 -m pytest -q tests/ml` → 37 passed
- `python3 -m pytest -q tests/strategies tests/ml` with `PYTHONPATH=/tmp/nopyspark` → 150 passed
- `python3 -m pytest -q tests/strategies/test_robustness_round3.py` → 6 passed (guard)
- `git stash` (revert to HEAD) → guard test FAILS (expected) → `git stash pop` (restore) → guard test PASSES

## Non-blocking notes
- The `run_cost_stress`, `run_universe_stress`, `run_parameter_stress` imports in the runner are unused (the runner has its own inline implementations). Not touched in this round.
- Capacity binding threshold uses `np.percentile` on the raw per-trade capacity distribution; the X-th percentile gives the book size below which >X% of trades can execute without hitting the ADV cap.