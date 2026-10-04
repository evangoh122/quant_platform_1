# BUILD: strategy round 10 (MiMo)

DeepSeek check7 (`.agents/deepseek/VERDICT-strategy-check7.md`): the round-9 ADV fix never reaches
the COST path. In `strategies/backtest.py:~345-346`, `run_backtest` rebuilds `adv_aligned` and calls
`fillna(0.0)` before `compute_costs`. So a dropped name's exit is still costed at 100% participation
(about 200 bps). The round-9 tests only exercised `cap_weight_changes_by_adv`, not costs. That's why
r8 equalled r7.

Fix:
- In `run_backtest`, build ONE ADV frame: per-symbol forward-fill of past values only, then
  `fillna(0)` only where a symbol has never had a value. Pass that SAME frame to both
  `cap_weight_changes_by_adv` and `compute_costs`.
- Remove every other `fillna(0)` on ADV in the call path. Grep and list each one in the verdict.

Tests, each failing on the current HEAD (prove it in /tmp):
- **End to end through `run_backtest`:** a name held, then dropped from the universe, with NaN ADV
  after the drop. Assert the exit-day cost equals the cost computed with its LAST KNOWN ADV, not
  100% participation. Assert the exact bps.
- A name that never had an ADV is still charged at 100% participation (conservative).

Add `CHANGELOG[9]`. Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden;
- the same suite from `tests/`.

LF line endings only. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Leave no scratch
files. Commit with a descriptive message. Write `.agents/mimo/VERDICT-strategy-round10.md`. Claude
reruns live as r9; r9 SHOULD differ from r8 if any exits were affected.
