# VERDICT: strategy-check — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 1

```
===VERDICT START===
```

## Blocking findings

- [gold/06_gold_tradable_universe.sql:75-78] The `history` gate counts calendar
  sessions, not the symbol's own trading sessions. `history` is
  `COUNT(*) OVER (PARTITION BY symbol ORDER BY event_date ROWS BETWEEN UNBOUNDED
  PRECEDING AND 1 PRECEDING)` evaluated over `grid_bars` (lines 59-66), which is
  the dense `symbol × market_date` CROSS JOIN (lines 51-58). Every pre-listing
  row has `dollar_volume IS NULL`, and `COUNT(*)` counts those NULL rows, so a
  symbol's `history` equals the number of market sessions before `t` since the
  start of the whole calendar — not the number of sessions the symbol actually
  traded. The "minimum history (>= 252 sessions)" gate is therefore silently
  disabled for any symbol listed after the data start.
  → Concrete failure (verified live): 58 of 585 universe symbols have fewer than
  252 of their own sessions before their first universe date, 49 have fewer than
  100, and names such as `SPCH`, `DJT`, `EXE`, `ICCT`, `CRWV` enter the top-300
  after only **5** sessions (query: `COUNT(DISTINCT event_date)` in
  `bronze_ohlcv_day` for `event_date < first trade_date`). This is a regression
  from round 1: this lane's own round-1 verdict documented the gate working
  ("starts 252 trading days after the data start (min-history gate)"). Fix:
  count non-NULL dollar volume, e.g. `COUNT(dollar_volume) OVER (...)` or
  `SUM(CASE WHEN dollar_volume IS NOT NULL THEN 1 ELSE 0 END) OVER (...)`.

- [strategies/results/residual_reversion_r2.md:18] Claims
  "universe: top 300 ... recency 5, min history 252". The "min history 252" part
  is not enforced by the SQL above and is therefore not an accurate description
  of what ran.

## Non-blocking notes

- [gold/06_gold_tradable_universe.sql:51-58] The `UNION` branch
  `SELECT symbol, event_date AS market_date FROM bars` is redundant — the
  CROSS JOIN already emits every `(symbol, market_date)` pair. Harmless, but dead.
- [strategies/residual_reversion.py:107] `_rolling_lagged_sum` does
  `np.nan_to_num(x).cumsum()`, so a NaN return/factor inside the 60-day
  estimation window is still imputed as 0 in the beta cross-products. This is a
  narrower, pre-existing version of the round-1 "missing → 0" issue (the
  round-2 fix removed it from `compute_daily_returns` and `compute_industry_factor`
  but not from the rolling sums). It does not reintroduce cross-symbol leakage
  (each symbol's regression uses only its own columns), so it is not blocking,
  but a symbol with universe gaps still sees a slightly biased beta.
- [strategies/run_residual_reversion.py:298] The results header hardcodes
  "2023-01-04 → 2026-09-04"; the live universe actually ends 2026-09-18
  (verified: `MAX(trade_date)`). Cosmetic, but a claim not derived from the data.

## Verified correct (hardest first)

1. **Universe look-ahead is eliminated.** All three windows use `1 PRECEDING` as
   the right boundary (`med_adv_60d` 60 PRECEDING→1, `history` UNBOUNDED→1,
   `recency` 5 PRECEDING→1), and `information_available_ts` uses `cal.prev_date`
   (the session before `t`). A symbol's own future bars cannot affect its
   membership on `t`. `recency` correctly counts the last 5 *market sessions*
   (dense grid + `SUM(dollar_volume IS NOT NULL)`). Live: 300 members on each of
   930 days (min/median/max all 300), 279,000 rows.
2. **Industry factors are date-specific and NaN-preserving.** Independent proof
   under `/tmp/deepseek_proof_industry.py`: appending a symbol whose returns are
   NaN before day `d` leaves every industry factor, residual, and beta before `d`
   bit-identical (pandas `assert_series_equal` on all four names); the future
   symbol's own pre-`d` factor is NaN, and `compute_daily_returns` never fills
   NaN with 0.
3. **ADV cap constrains execution.** `run_backtest` applies
   `cap_weight_changes_by_adv` to the neutralised weights *before* P&L
   (`weights.shift(1)*returns`) and before `compute_costs` (turnover + borrow),
   so positions, P&L, and borrow are all on capped size; zero-ADV names never
   accumulate (cap = 0 → no change). Unit test `test_adv_cap_constrains_execution`
   covers the tiny-ADV and zero-ADV cases.
4. **Walk-forward is honest.** `max_hold` is selected on `train_dates` only
   (run_residual_reversion.py:245-255) and evaluated on `val_dates`;
   `purged_walk_forward_splits` purges overlapping label windows and embargoes
   `max(hold_candidates)=10`; `n_trials = len(hold_candidates) = 3`, passed to
   both `portfolio_metrics` and `_deflated_sharpe`.
5. **r2.md numbers are internally consistent with the live rebuild** (net Sharpe
   -0.359, OOS -0.514, DSR 0.000, gated +0.007 — matching the coordinator's
   independent measurement), aside from the two findings above.

## Checks run

- `python3 -m pytest tests/strategies -q` (from WSL) → **24 passed**, 16 warnings
- `python3 /tmp/deepseek_proof_industry.py` (PYTHONPATH=repo) → **PASS**
  (factors/residuals/betas before d invariant to a future-listed symbol)
- Live Databricks SQL (`evangohsg`):
  - universe shape → 930 days, 2023-01-04 → 2026-09-18, 279,000 rows, 300/day
  - `sessions strictly before first universe date` → 58/585 symbols < 252, 49 < 100,
    min 5 (SPCH, DJT, EXE, ICCT, CRWV) — the blocking finding above

```
===VERDICT END===
```
