===VERDICT START===
# VERDICT: strategy-residual-reversion round 5 (CodeRabbit fixes + results) — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 5

Reviewed the code changed since `b115443` on `slice/strategy-residual-reversion`.
All scratch work under `/tmp`; nothing committed or pushed. Live gold tables were
re-queried directly against the SQL warehouse to check Claude's numbers.

## Blocking findings

- [strategies/backtest.py:97] The "increase" test `np.abs(cur) > np.abs(prev) + 1e-15`
  does **not** correctly cap the new leg on a sign flip, contradicting the module's
  own docstring ("increases are still capped", "reductions toward zero are never
  capped"). Two concrete failure modes, both reproduced numerically under `/tmp`:

  1. *Equal-magnitude flip is uncapped.* A liquid name held long `+0.4` (established)
     that flips to `-0.4` the next day has `|cur| == |prev|`, so `increasing` is
     `False` and the new short leg opens fully in one day. The trade is `|Δ|=0.8`
     notional (close `0.4` + open `0.4` short) with **zero** ADV capping — the new
     short leg that the request says "should be capped" is not. Reproduced: input
     `+0.4 → -0.4` with a liquid name yields weights `[0.4, -0.4, ...]` unchanged.

  2. *The reduction leg is capped on a magnitude-increasing flip.* A name held long
     `+0.06` (built under the cap) flipping to `-0.4` has `|target|=0.4 > |prev|=0.06`,
     so the code caps the *whole* `|Δ|` toward the target, producing `+0.04` on the
     first flip day — it caps the *close-out of the long* (which the docstring says
     must never be capped) and defers opening the short until the long is fully closed.
     Reproduced: `+0.4,+0.4,+0.4 → -0.4` at `0.02/day` cap yields
     `[0.02, 0.04, 0.06, 0.04, 0.02, 0.0]` (still long on the flip days).

  Root cause: `abs(cur) > abs(prev)` conflates "net magnitude increase" with "the new
  opposite leg must be capped". The fix is to decompose the daily change into the
  close-out leg (always free, toward 0) and the open leg (the portion extending past
  0 in the new direction, which alone should be capped). Practical impact on *this*
  backtest is small (the 1%-of-ADV budget for top-300 names is far above their
  neutralised weights, so the cap rarely binds), but the stated invariant is wrong in
  both directions and the request explicitly requires the new short leg be capped.

## Answers to the check questions

### 1. `strategies/residual_reversion.py` — validity mask
- **OLS normal equations == `np.linalg.lstsq` on valid rows: YES.** Proved on random
  data with injected NaN gaps in `y`, `m`, `f` (300 rows, 197 eligible windows):
  `max |coef err| = 4.77e-15`. The zeroed cross-products (`residual_reversion.py:141-155`)
  with per-window `n_valid` (line 155, 163) reproduce `lstsq` on the valid rows exactly.
  The existing `test_nan_returns_not_counted_as_zeros` also asserts this for one window.
- **Window still lagged: YES.** Perturbing `y[150]` leaves `beta_mkt[150]`/`beta_ind[150]`
  unchanged but moves `residual[150]`; `_rolling_lagged_sum` sums `[t-window, t)`.
- **`sigma` starvation: NON-BLOCKING.** `sigma` = `_trailing_std` (line 244) uses
  `rolling(window, min_periods=window)` on residuals that are NaN on gap days, so one
  gap makes `sigma` NaN for the following 60 days. With ~42 gaps in a 300-row series,
  `beta` is non-NaN on 240 days but `sigma` on only 60 — it does starve signals. It is
  *inconsistent* with the beta's `min_obs = ceil(0.8*window) = 48` (the regression
  tolerates 20% missing rows; sigma requires 100%). But it is only conservative (never
  fabricates a signal, no look-ahead), and for the liquid top-300 universe names trade
  continuously, so it reduces to a warm-up effect. Recommend aligning `min_periods` to
  `min_obs` for consistency, but it does not block.

### 2. `strategies/backtest.py` — ADV cap
- **Only increases capped: YES** for the non-flip case (`increasing` gate, line 97).
- **Sign-flip "increase" definition: NOT correct** — see blocking finding above.
- **Forward-filled ADV uses only past data: YES, but dead in production.** `ffill()`
  (line 90) is past-data-only (no look-ahead), *however* `run_backtest` already calls
  `adv.reindex(...).fillna(0.0)` at line 311 before passing ADV to
  `cap_weight_changes_by_adv`, so by the time `ffill()` runs there are no NaN values
  left to fill — the forward-fill is neutralised and the docstring's "last known ADV is
  used" claim is not actually exercised. Harmless, because exits never consult ADV
  (reductions are uncapped), but the changelog/result doc overstate the mechanism.
- **Dropped name exits: PROVEN.** `filter_to_universe` zeroes the target, so
  `|cur|=0 < |prev|` → `increasing=False` → full liquidation with no cap. Confirmed by
  `test_position_liquidates_when_adv_becomes_nan` (passes) and by code path (line 302-312).

### 3. `gold/06`, `gold/07` SQL guards vs `strategies/universe.py`
- The partial-window guards match the pandas references:
  - `06:73-81` `COUNT(dollar_volume) OVER (...60 PRECEDING AND 1 PRECEDING) = 60`
    ⟺ `rolling(60, min_periods=60).median().shift(1)` (universe.py:39-41).
  - `07:72-78` `COUNT(rsp_spy_ratio) OVER (49 PRECEDING AND CURRENT ROW) >= 50`
    ⟺ `rolling(50, min_periods=50).mean()` (test_universe.py:168).
- **Live tables agree with Claude's numbers (re-queried directly):**
  `gold_tradable_universe` = 281,700 rows = 300 names × **939** dates exactly
  (min=300, max=300 per day, 557 distinct symbols), `MIN/MAX trade_date` =
  `2023-01-04` / `2026-10-01`, **0** NULL `med_adv_60d` among members.
  `gold_regime_features` = 1,191 rows (`2022-01-03` → `2026-10-01`), **49** NULL
  `rsp_spy_ratio_sma50` rows, first non-NULL = **2022-03-15**. All consistent with the SQL.

### 4. Results `strategies/results/residual_reversion_r4.md`
- **Internally consistent:** baseline `net` ann return `-0.0884`/Sharpe `-0.403`/
  `net@2x -0.549` are reproduced verbatim in the ablation "unconditioned" column;
  the caveat's gated `net@2x = -0.264` matches the table; walk-forward OOS Sharpe
  `-0.519` → DSR `0.000` is coherent (negative Sharpe → DSR≈0).
- **Changelog accurate:** the 4 rows match the 4 actual code changes in this round
  (verified against the diff). Minor overstatement: row 2's "ADV is forward-filled
  ... so a position can always be reduced to zero" — the exit is achieved by the
  "only increases capped" rule, not by the (dead) forward-fill.
- **Caveat states no edge: YES.** It says the gated comparison is "in-sample /
  full-period exploratory", "not evidence of an edge", cites gated `net@2x = -0.264`
  and DSR `0.000`, and warns against live deployment without OOS validation.
- **No unsupported claims found.** The header date range, `939 trading days`, and
  fold/trial counts all match the code (`hold_candidates=[3,5,10]`, `n_splits=5`) and
  the live universe.

## Non-blocking notes
- `gold/06:107` uses `ROW_NUMBER ... ORDER BY med_adv_60d DESC, symbol` while the pandas
  reference uses `rank(method='first')`; tie-breaking can select a slightly different
  300 on exact median ties (rare, pre-existing, not this round's change).
- The gated-ablation DSR uses `n_trials=3`, under-counting the breadth gate as a 4th
  trial; irrelevant since the ablation is caveated as in-sample and DSR is already 0.

## Checks run
```
$ python3 -m pytest -q tests/strategies tests/ml
71 passed, 34 warnings in 72.01s

$ python3 /tmp/verify_r5.py           # OLS vs lstsq + lagged beta + sigma starvation
OLS equivalence: checked 197 windows, max|coef err|= 4.773959005888173e-15
lagged-window no-lookahead: OK
days beta non-NaN but sigma NaN: 137 ; days sigma non-NaN: 60

$ python3 /tmp/verify_adv.py /tmp/verify_adv2.py   # sign-flip reproduction (blocking)

$ python3 /tmp/verify_live.py         # live gold tables (Databricks, profile evangohsg)
total rows 281700 ; distinct dates 939 ; 300 names/day (min=max) ; NULL medians 0
SMA50 first non-null 2022-03-15 ; NULL SMA50 rows 49 ; regime rows 1191
```
===VERDICT END===
