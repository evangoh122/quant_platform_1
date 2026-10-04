===VERDICT START===
# VERDICT: strategy-round11 check9 — DeepSeek
**Status:** APPROVED
**Round:** 11 (check9)

Read-only re-check of commit `0507f68` (round 11) against the "Re-check after round 11"
section of `CHECK-strategy-round9.md`, plus a re-confirmation of the round-9 and round-10
items carried forward. Traced `main` → `run_one` → `run_backtest`, confirmed all backtest
call sites consume `valuation_returns` while signal construction still uses the masked
`returns`, verified the end-to-end exit-day test asserts exact P&L, audited the split/
corporate-actions context, and re-ran the full required suites (normal, pyspark-hidden,
cwd=test). Nothing committed or pushed.

## Blocking findings

None. All three round-11 re-check items pass, and the round-9/10 items remain closed.

## 1. Every `run_backtest` / `run_one` call site uses `valuation_returns` — PASS

`build_signals` (`strategies/run_residual_reversion.py:170-178`) now returns two explicit
keys so the masked/unmasked frames cannot be confused again:
- `"returns"` → `tradeable_returns = returns[tradeable].where(mask)` (`:158`) — the PIT-masked
  frame, used **only** for signal construction;
- `"valuation_returns"` → `returns[tradeable]` (`:172`) — the unmasked frame, used for the backtest.

The only production path is `main()` → `run_one()` → `run_backtest()`
(`run_residual_reversion.py:198`). All four `run_one` call sites pass `valuation_returns`:
- `:380` walk-forward training `run_one(signals[h]["positions"], signals[h]["valuation_returns"], …)`
- `:387` walk-forward validation `run_one(signals[best_h]["positions"], signals[best_h]["valuation_returns"], …)`
- `:402` `base_res = run_one(base_pos, signals[h_default]["valuation_returns"], …)`
- `:404` `gated_res = run_one(gated_positions, signals[h_default]["valuation_returns"], …)`

No other production caller of `run_one`/`run_backtest` exists (the only remaining `run_backtest`
references are in `tests/`). `strategies/residual_reversion.py:build_signal` (`:323`) returns raw
`returns` but does not call `run_backtest` and is not imported by the runner, so it is out of scope.

## 2. Signals are unchanged — PASS

The signal path is untouched by round 11: `compute_industry_factor(tradeable_returns, …)` (`:164`),
`compute_residuals(tradeable_returns, market, ind_factor, …)` (`:166-167`) and
`generate_signals(res["s_score"], …)` (`:168-169`) all still consume the masked
`tradeable_returns`. `valuation_returns` is an additive key in the returned dict; it does not feed
s-scores, residuals, or positions. `test_signals_unchanged_by_valuation_returns_fix` pins this:
masked `returns["A"]` is NaN on the drop day while `valuation_returns["A"]` is valid, and positions
remain `{-1, 0, +1}`.

## 3. End-to-end exit-day test asserts exact P&L — PASS

`tests/strategies/test_run_residual_reversion.py::test_exit_day_pnl_includes_held_name_return`
holds long A / short B, drops A from the universe at day 10, and asserts the day-10 gross P&L
**exactly**: `new_gross_exit == pytest.approx(w_prev_a*0.01 + w_prev_b*0.01, abs=1e-12)`. It also
proves the masked path drops A's return (`old_gross_exit ≈ w_prev_b*0.01`) and that unmasked ≠ masked.
The companion `test_missing_close_contributes_zero_not_fabricated` pins that a genuinely missing close
still contributes 0 (NaN is skipped by `.sum()`), not a fabricated return. Both are exact-value
assertions and would fail on the pre-round-11 (masked-returns) code, so the regression is genuinely
proven. Round 11 added exactly 3 tests → total `tests/strategies tests/ml` went 86 → 89.

## 4. Split / corporate-actions context (bronze_ohlcv_day is unadjusted) — CONFIRMED

`compute_daily_returns` (`strategies/residual_reversion.py:50-58`) is `prices.pct_change(fill_method=None)`
on unadjusted closes, so a split day (e.g. AMZN 2022-06-06 −95%) flows straight into both
`valuation_returns` (→ P&L) and, equally, the masked `returns` (→ residuals/s-scores). The round-11
logic is **correct given correct inputs**: it uses the unmasked close-to-close return for a held
name's exit day and skips only genuine NaNs. The remaining defect is a data-quality one, not a
code-logic one.

**Exact call site that must switch to adjusted closes once `slice/corporate-actions` lands
(`silver_ohlcv_day_adjusted`):**
- `strategies/run_residual_reversion.py:78-86` — the single `closes = _fetch(w, …)` query
  `SELECT symbol, event_date, close FROM {FQN}.bronze_ohlcv_day`. This is the **only** ingestion
  point for closes in this strategy; everything downstream (`build_wide` `:101` → `compute_daily_returns`
  `:147` → `build_signals` `:147`/`:172` → `valuation_returns`/`returns` → `run_one` → `run_backtest`)
  is derived from `closes`, so a one-line source swap propagates to both the signal and valuation
  paths automatically. No separate change is needed in `run_one`/`run_backtest`. No live rerun until
  the adjusted table exists (per the brief).

## Carried-forward round-9 / round-10 items (re-confirmed)

- **Read-only `.to_numpy()`/`.values` audit** — the only in-place write site remains
  `strategies/backtest.py:84` (`out = weights.to_numpy(dtype=float, copy=True)` → `out[i] = …`),
  now a copy. All other `strategies/`/`ml/` sites are read-only or write a freshly allocated array.
- **ADV ffill past-only** — `backtest.py:343-344` (`adv_aligned = adv.reindex(…).ffill().fillna(0.0)`)
  and `:353` (`adv_for_costs = adv_aligned.reindex(returns.index, …).ffill().fillna(0.0)`): `fillna(0)`
  follows `.ffill()` in both, so it can only zero never-seen symbols. `ffill` is a forward fill of
  past values only; the reindex-then-ffill order cannot introduce look-ahead. The SAME frame feeds
  both the cap (`:345`) and costs (`:355`).
- **check7 finding fixed** — the pre-round-10 cost-path `fillna(0.0)` rebuild is gone; dropped-name
  exits are costed at last-known ADV, proven by `test_exit_cost_uses_last_known_adv_not_100pct_participation`.
- **r8 == r7 plausibility** — unchanged conclusion (see check8): the round-8/9 cost path was a no-op
  under pandas 2.x, and NaN ADV had no prior non-NaN to fill from, so r8 ≡ r7 (−0.382/−0.636/DSR 0);
  the result only moved in r9 (net −0.363, OOS −0.623), which the r9 report shows consistently.
- **Test paths cwd-independent** — `tests/strategies/test_universe.py:238` and
  `tests/lakebase/test_migrations.py:140` resolve via `Path(__file__).resolve().parents[2]`.

## Non-blocking notes

- `compute_costs` docstring (`backtest.py:182`) still says "unknown ADV → 100% participation";
  accurate for never-seen symbols but stale for dropped names now forward-filled. Cosmetic only.
- Because `bronze_ohlcv_day` is unadjusted, the **signals** (residuals/s-scores) are also exposed to
  split artifacts — not just P&L. Switching the `:78-86` fetch to `silver_ohlcv_day_adjusted` fixes
  both at once, which is worth stating explicitly in the corporate-actions lane hand-off.

## Checks run

- `python3 -m pytest -q tests/strategies tests/ml` (repo root) → **89 passed**, 34 warnings
- same suite with pyspark hidden (`PYTHONPATH=/tmp/pyspark_blocker`, `pyspark.py` raises ImportError)
  → **89 passed**, 34 warnings
- `python3 -m pytest -q tests/strategies/test_run_residual_reversion.py -v` → **9 passed**
  (6 prior + 3 round-11: exit-day P&L, missing-close-zero, signals-unchanged)
- `cd /tmp && python3 -m pytest -q /home/jianj/code/qp1-strat2/tests/strategies/test_universe.py`
  → **8 passed** (cwd-independent path resolution confirmed)
- `grep` for `run_one(`/`run_backtest(`/`valuation_returns` → 4 production call sites all use
  `valuation_returns`; no stale masked-`returns` backtest caller
- `grep` for `.to_numpy(`/`.values` in `strategies/`, `ml/` → single in-place write site
  (`backtest.py:84`, now `copy=True`)
- `grep` for `bronze_ohlcv_day`/`silver_ohlcv_day_adjusted` → single closes fetch at
  `run_residual_reversion.py:78-86`; no `silver_ohlcv_day_adjusted` exists yet
===VERDICT END===
