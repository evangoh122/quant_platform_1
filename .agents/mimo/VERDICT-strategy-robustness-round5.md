===VERDICT START===
# VERDICT: strategy-robustness-round5 — MiMo
**Status:** APPROVED
**Round:** 5

Committed `cc2f9e0` on `slice/strategy-robustness`. All scratch under `/tmp`.
Nothing pushed to main. Working tree clean.

## Blocking findings addressed

1. **[strategies/run_residual_reversion.py:574,587-588,760] Per-fold drop-top-3 now
   selects by realised P&L (lagged_weight × tradeable returns), not residual returns.**
   - Added `"trade_returns": sig.get("returns")` to `_run_variant` return dict (line 760).
   - Changed per-fold path to read `hold_vr["trade_returns"]` (line 574).
   - Updated comment to clarify "realised P&L (lagged weights × tradeable returns,
     same as run_one trades)" (line 586-587).
   - `remove_top_pnl_contributors` (robustness.py:212) already uses raw `returns`;
     both paths now share the same returns basis.

2. **[strategies/robustness.py:836-845] Rank IC table now discloses method and
   shows effective_n.**
   - Added note: `_t-stat method: Newey-West HAC (Bartlett kernel, lag = H-1)._`
   - Added `eff. n` column to the table header and data rows.
   - Uses `ric.get("effective_n", ric["n"])` for backward compatibility.

## Non-blocking notes

- **[strategies/run_residual_reversion.py:617-618]** `except Exception: pass`
  silently falls back to `oos_full` on trimmed backtest failure — carried from
  round-4, out of scope.
- **[strategies/robustness.py:206-212]** `remove_top_pnl_contributors` sums
  gross of cost allocation — pre-existing, out of scope.
- **[strategies/run_residual_reversion.py:760]** `trade_returns` and
  `residual_returns` are now stored under distinct keys to prevent future
  confusion.

## Tests

New test file `tests/strategies/test_robustness_round5.py` with 7 tests:
- 6 tests FAIL on pre-round-5 HEAD (proven in /tmp).
- 1 test (`test_top3_by_realised_differs_from_residual_in_market_dominated_panel`)
  is a property test that passes on any HEAD (validates the synthetic probe
  setup).

## Checks run

```
$ python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
165 passed, 34 warnings in 93.77s

$ PYTHONPATH=/tmp/nopyspark python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml
   (sitecustomize sets pyspark/pyspark.sql/pyspark.sql.functions/pyspark.sql.types = None)
165 passed, 34 warnings in 83.01s

# probe: pre-round-5 tests fail as expected
$ python3 -m pytest -q tests/strategies/test_robustness_round5.py -p no:cacheprovider
6 failed, 1 passed (before fix)
7 passed (after fix)
```
===VERDICT END===