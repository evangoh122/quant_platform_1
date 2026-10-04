# VERDICT: strategy round 10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings
None.

## Fix applied

`strategies/backtest.py` `run_backtest`: built ONE ADV frame with per-symbol forward-fill then `fillna(0)` for never-seen symbols. Passed the SAME frame to both `cap_weight_changes_by_adv` and `compute_costs`. Previously, `compute_costs` received a separate ADV frame with `fillna(0.0)` on all NaN, so a dropped name's exit was costed at 100% participation (~202 bps) instead of its last known ADV (~12 bps).

## fillna(0) on ADV in the call path — exhaustive list

| File | Line | Context | Verdict |
|------|------|---------|---------|
| `strategies/backtest.py` | 89 | `adv_ff.fillna(0.0)` inside `cap_weight_changes_by_adv` | OK — idempotent since we pre-ffill; never-seen symbols correctly get 0 |
| `strategies/backtest.py` | 344 | `adv_aligned.ffill().fillna(0.0)` | **The fix** — single frame for both cap and costs |
| `strategies/backtest.py` | 353 | `adv_for_costs = adv_aligned.reindex(...).ffill().fillna(0.0)` | **The fix** — reindexed copy for costs, same semantics |
| `strategies/backtest.py` | 40 | `desired.shift(1).fillna(0.0)` | Unrelated — positions, not ADV |
| `strategies/backtest.py` | 348 | `weights.shift(1).fillna(0.0)` | Unrelated — weights, not ADV |
| `strategies/run_residual_reversion.py` | 193 | Comment: "Do NOT fillna(0) here" | Already correct — ADV passed with NaN |

No other `fillna(0)` on ADV exists in the call path.

## Tests

Two new tests in `tests/strategies/test_backtest.py`:

1. **`test_exit_cost_uses_last_known_adv_not_100pct_participation`** — end-to-end through `run_backtest`: name held, then dropped from universe with NaN ADV. Asserts exit-day cost uses last known ADV (1e8), not 100% participation. **Failed on old code** (0.01616 vs 0.00144), **passes with fix**.

2. **`test_never_held_adv_name_charged_100pct_participation`** — `compute_costs` directly with ADV=0. Asserts 100% participation (conservative fallback). Passes on both old and new code (inherent behavior of `compute_costs`).

## Checks run

```
python3 -m pytest -q tests/strategies tests/ml → 86 passed
PYTHONPATH="" python3 -m pytest -q tests/strategies tests/ml → 86 passed (pyspark hidden)
python3 -m pytest -q tests/ → 582 passed, 67 skipped, 22 errors (lakebase endpoint disabled — infrastructure)
```

## CHANGELOG
Added `CHANGELOG[9]` to `strategies/run_residual_reversion.py`.

## Note
`.agents/dispatch.sh` shows a file mode change (100755 → 100644) in `git diff`. This is a WSL/Windows filesystem artifact — no content was modified. The file was not touched per the BUILD request.