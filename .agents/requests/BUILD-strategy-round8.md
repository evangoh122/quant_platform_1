# BUILD: strategy round 8, Codex final-validation findings (MiMo)

Codex returned CHANGES_REQUESTED (`.agents/codex/VERDICT-strategy-final.md`). Read it. Fix all four.
Each fix needs a test that FAILS on the current HEAD. Prove it in a /tmp copy and paste the output in
the verdict.

## 1. [Blocking] `strategies/backtest.py:~208-216`: exit/reduction costs are undercharged
`cap_weight_changes_by_adv` lets the full close leg execute (round 7), but `compute_costs` then runs
the executed notional through `scale_order_to_adv_cap` and charges costs on at most 1% of ADV.

Fix: charge costs on the **actually executed** notional, `|w[t] - w[t-1]| * book_capital`, after the
cap step. Never re-cap it inside the cost computation. If the cost model has a participation-dependent
impact term, it must use the true participation (executed / ADV), even above the cap. Exits can be
expensive; that is correct.

Tests:
- a large exit (executed notional = 5% of ADV) is charged on the full notional;
- costs are never below `(commission+spread+slippage) bps × executed notional`.

## 2. [Blocking] `strategies/universe.py:36-48`: pandas doesn't match the SQL dense-grid semantics
`gold/06` builds a dense symbol × market-date grid, so missing sessions are NULL rows inside the
windows. Pandas rolls only over the rows present.

Fix: reindex each symbol onto the full market calendar (the union of dates present in the panel, or
an explicit calendar argument) before rolling. Then the median window, recency count and history
count all match the SQL.

Test: the sparse-input case Codex gave (one absent session → symbol B must NOT be admitted for the
next 5 dates). Dense and sparse inputs must agree with a hand-computed SQL-semantics expectation.

## 3. [Blocking] `gold/07_gold_regime_features.sql:~89-97`: partial z-score window
The guard uses `COUNT(*)`, but `AVG`/`STDDEV` ignore NULL `rsp_spy_ratio`. Use
`COUNT(rsp_spy_ratio) OVER (same window) >= 252`.

Test: a SQL text/structure test that asserts the guard counts the column (same style as the round-5
SQL tests).

## 4. [Report] Leverage wording
`strategies/run_residual_reversion.py:~394` says "target gross 1.0 (100% long / 100% short)". With
`sum|w| = 1` and dollar neutrality it is **50% long / 50% short**. Fix the text. Add a test that the
rendered configuration line says 50%/50% when gross=1.0.

## Then
- Add `CHANGELOG[7]` rows.
- Run `python3 -m pytest -q tests/strategies tests/ml`, and the same suite with pyspark hidden
  (`PYTHONPATH=/tmp/nopyspark`).
- Claude will rebuild `gold_regime_features` and rerun live as r7.
- LF line endings. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Commit. Write
  `.agents/mimo/VERDICT-strategy-round8.md`.
