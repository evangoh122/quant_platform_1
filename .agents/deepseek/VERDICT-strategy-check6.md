===VERDICT START===
# VERDICT: strategy-round8 check6 — DeepSeek
**Status:** APPROVED
**Round:** 8 (check6)

Read-only re-check of commit `9b66b39` (fixes the four Codex findings) against the
`CHECK-strategy-round8.md` brief. Verified the fix diffs, ran the full required suites (normal +
pyspark-hidden), and produced independent `/tmp` proofs for each of the five checks. Nothing
committed or pushed.

## Blocking findings

None. All four Codex findings are fixed; the five checks below pass.

## 1. Costs on the executed notional — FIXED

- `strategies/backtest.py:212-221` removed the `scale_order_to_adv_cap` re-cap. Costs are now
  charged on the **actual executed notional** (`|dw| * book_capital`) with slippage computed on the
  **true participation** `notional / ADV`, uncapped.
- Independent proof (`/tmp/proof_check1.py`): a $5M exit on a $10M-ADV name (participation 0.5)
  is charged `0.005100` (bps = 0.5 + 1.5 + 2·(0.5/0.01) = 102) — the true participation drives a
  100 bps slippage term, not a capped 2 bps. `match=True`.
- **Borrow still charged on shorts** (`strategies/backtest.py:224-230`, unchanged): short book
  `borrow_cost > 0` on every bar; long-only book `borrow_cost == 0`. `match=True`.
- **ADV cap property test passes**: `test_adv_cap_property_invariants` → PASS (seeded 500 sequences,
  0 violations). The cost change touches `compute_costs` only, not `cap_weight_changes_by_adv`.

## 2. `universe.py` dense grid — FIXED, no look-ahead

- `strategies/universe.py:36-46` reindexes every symbol onto the full market calendar
  (`pivot` + `reindex(all_dates)` + `melt`) before the `groupby`/`rolling`. A missing session is now
  a NaN row (matching the SQL `grid` NULL row), not an absent row.
- Independent proof (`/tmp/proof_check2.py`) reproduces Codex's sparse case: symbol `S00` missing
  one session at day 30 is **NOT admitted for dates 31-35** (`gap_dates.isdisjoint(sparse) == True`),
  and dense still admits them (`issubset(dense) == True`).
- **Dense == sparse** for all 9 other symbols (calendar reindex recovers the SQL dense-grid
  semantics exactly).
- **No calendar-source look-ahead**: the calendar `all_dates` is the union of all panel dates, but
  every rolling computation is trailing (`rolling(...).shift(1)` / `cumsum().shift(1)`), and
  `screen_universe` uses `event_date < trade_date`. Proof: truncating the panel to a cutoff date and
  recomputing leaves membership for all dates ≤ cutoff **identical** (`invariant == True`). The
  future calendar dates only add trailing NaN rows, never inject future dollar volume into a past
  window. This mirrors `gold/06` (which also builds the grid from `SELECT DISTINCT event_date`).

## 3. `gold/07` z-score guard — FIXED

- `gold/07_gold_regime_features.sql:89` now uses `COUNT(rsp_spy_ratio)` (and `:72` for the SMA50
  guard); no `COUNT(*)` remains in the file. A 252-row window with any NULL `rsp_spy_ratio` is now
  excluded, consistent with `AVG`/`STDDEV` ignoring NULLs.
- Live-table numbers are arithmetically consistent: `366 + 239 + 586 = 1191` rows. I cannot
  independently re-query the live warehouse in this read-only check, so the exact
  z-score-from-2023-01-03 start date and the regime split are taken as stated by Claude; the SQL
  change itself and the count arithmetic both verify.

## 4. Leverage wording — FIXED

- `strategies/run_residual_reversion.py:416` and `residual_reversion_r7.md:21` both say
  "50% long / 50% short". No `100% long / 100% short` string remains in the source or in r7.
  (The r1–r6 result files still carry the old wording, but those are immutable historical records,
  not a defect.)

## 5. r7 results — internally consistent, changelog accurate, no edge, costs rose

- `CHANGELOG[7]` has exactly the four fix entries, and `residual_reversion_r7.md` "What changed vs
  r6" reproduces their rationale text verbatim.
- **No edge stated**: the gated comparison is labelled in-sample/full-period with an explicit
  caveat; gated net Sharpe @2× = -0.278, deflated Sharpe = 0.000, walk-forward OOS net Sharpe =
  -0.636 (negative), OOS annualised return -0.2399.
- **Costs rose vs r6 as expected**: net ann return -0.0803 → **-0.0846**; net Sharpe -0.363 →
  **-0.382**; net@2× -0.1129 → **-0.1214**; max drawdown -0.5121 → -0.5162. Gross return is
  unchanged (-0.0478) because gross is pre-cost — correct.
- **Internal arithmetic consistent**: implied annualised vol from ann-return/Sharpe is 0.2213
  (gross), 0.2215 (net), 0.2215 (net@2×) — the same volatility across all three, as it must be.

## Non-blocking notes

- `strategies/backtest.py:181-184` `compute_costs` docstring is stale: it still says the order "is
  first capped at 1 % of the name's ADV (`scale_order_to_adv_cap`)". That is no longer true.
- `strategies/backtest.py:27-28` imports `cost_per_trade` and `scale_order_to_adv_cap`, neither of
  which is now called in this module (`cost_per_trade` is still used in `ml/evaluate.py`).
- Divergent cost formula: `cost_model.cost_per_trade` still caps participation at
  `adv_participation_cap` (line 61), while `compute_costs` now inlines an uncapped variant. Not a
  defect (the backtest semantics are now correct and tested), but two implementations of the same
  formula will drift.

## Checks run

- `python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml` → 83 passed, 34 warnings
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml` → 83 passed, 34 warnings
- `python3 /tmp/proof_check1.py` → 1a match=True; 1b borrow>0 short / ==0 long; 100 bps slippage
- `python3 /tmp/proof_check2.py` → 2a gap excluded 5 dates; 2b dense==sparse; 2c past-invariant=True
- `grep` for `100% long` / `COUNT(*)` → absent from source + r7 + gold/07
===VERDICT END===
