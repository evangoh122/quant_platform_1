===VERDICT START===
# VERDICT: strategy-residual-reversion (round-4 re-check) — DeepSeek
**Status:** APPROVED
**Round:** 4

## Blocking findings
None.

## Verification (hardest first, independent)

### 1. Universe SQL — no remaining look-ahead
`gold/06_gold_tradable_universe.sql:71-84` computes every gate with window frames
ending strictly before the current row: `med_adv_60d` (`ROWS BETWEEN 60 PRECEDING AND
1 PRECEDING`, line 71-74), `history` (`UNBOUNDED PRECEDING AND 1 PRECEDING`, now
`COUNT(dollar_volume)`, line 75-78), `recency` (`5 PRECEDING AND 1 PRECEDING`,
line 81-84). The dense `grid` (line 51-58) only widens the *market* calendar; a
symbol's own future bars are excluded from its membership on day `t` because the
frames are `PRECEDING`-only. No path uses `CURRENT ROW`/`FOLLOWING`. PASS.

### 2. Industry factors — NaN propagation + no cross-contamination
Proved with a mutated copy under `/tmp` (script run inline in WSL): two industries,
one with a `LATE` symbol listing after day 6.
- `compute_industry_factor` (`strategies/residual_reversion.py:82-93`) excludes NaN from
  both `industry_totals` and the per-date count `n_ind`, so a pre-listing symbol
  contributes 0 to sum and count.
- Result: `max |factor diff| before listing = 0.0` and `max |residual diff| before
  listing = 0.0`. A symbol listed after `d` cannot change factors/residuals before `d`. PASS.
- NaN stays NaN: with 2+ valid peers, a NaN symbol's factor and residual stay NaN
  (verified). PASS.

### 3. ADV cap constrains positions, P&L, and borrow
`strategies/backtest.py:296-304`: `weights` are first passed through
`cap_weight_changes_by_adv` (line 301), and it is the *capped* weights that feed
`gross` (`weights.shift(1) * returns`, line 304). Costs/borrow are then computed on the
same capped weights (`compute_costs(weights, …)`, lines 309-314; borrow uses the capped
`w[s]` at `backtest.py:192`). Zero-ADV names get `cap=0` (`cost_model.py:135-140`) and
cannot accumulate a position (`backtest.py:94`). PASS.

### 4. Walk-forward — train-only selection, purge/embargo, honest trial count
`strategies/run_residual_reversion.py:244-261`: per fold, `best_h` is chosen by the
net Sharpe on `train_dates` only (lines 249-255), then evaluated OOS on `val_dates`
(line 259). `purged_walk_forward_splits` (`ml/train.py:68-120`) purges overlapping
`[start, start+15d]` label windows and applies `embargo=10`. `n_trials =
len(hold_candidates) = 3` (`run_residual_reversion.py:242`) is passed honestly to
`deflated_sharpe_ratio` (`ml/evaluate.py:95-116`). PASS.

### 5. r2.md vs what ran
`strategies/results/residual_reversion_r2.md:18` states "min history 252", but the SQL
that produced its numbers used `COUNT(*)` over the dense grid (pre-round-4), so that
config line was **not** effectively enforced. This is now explicitly corrected in
`residual_reversion_r3.md` (instability table + note). r2.md is a superseded artifact;
its remaining inaccurate line is documented as such in r3. Non-blocking (see notes).

## Non-blocking notes
- `strategies/universe.py:42-44` (round-4 change) is a **no-op**: I verified
  `s.rolling(1).count().cumsum()` and `s.notna().cumsum()` are identical even with NaN.
  The pandas reference never built the dense grid, so it never reproduced the SQL
  `COUNT(*)` bug. The new `test_history_gate_counts_own_sessions_not_grid_rows`
  (`tests/strategies/test_universe.py:77-107`) would pass under the *old* code too — it
  does not actually reproduce/guard the SQL defect. The real fix is SQL-only
  (`gold/06_gold_tradable_universe.sql:75`), verified live by MiMo (0 members < 252
  sessions). The offline spec remains weaker than claimed.
- `strategies/universe.py:46-48` recency uses `s.rolling(5).count()` on the symbol's own
  rows (non-dense panel), not the SQL's dense market-session count. The reference does
  not exercise the SQL's staleness filter; `test_recency_filter_excludes_stale_symbol`
  passes trivially because a stale symbol has no later rows in a non-dense panel.
- `strategies/residual_reversion.py:107` `_rolling_lagged_sum` imputes NaN as 0 in beta
  cross-products (pre-existing, previously flagged; narrower, no cross-symbol leakage).
- `strategies/residual_reversion.py:89` industry factor guard `n > 1` yields factor 0.0
  (not NaN) for a NaN symbol with exactly one valid peer — harmless, that symbol's
  residual is NaN anyway.
- Gated-ablation DSR uses `n_trials=3`, which under-counts the breadth gate as a 4th
  trial; irrelevant since DSR is already 0.000 and the ablation is caveated as in-sample.

## Checks run
- `python3 -m pytest tests/strategies -q` → **25 passed**, 16 warnings (WSL)
- `python3` mutated-copy proof for industry-factor invariance → diff 0.0 / 0.0 (PASS)
- `python3` `rolling(1).count()` vs `notna().cumsum()` equivalence → identical (PASS)
===VERDICT END===
