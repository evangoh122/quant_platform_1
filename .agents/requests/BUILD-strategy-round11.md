# BUILD: strategy round 11, CodeRabbit Major on PR #16 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

CodeRabbit (latest review on #16), verified by Claude: in `strategies/run_residual_reversion.py:~140-160`,
`build_signals` masks returns to the PIT universe (`tradeable_returns = returns[tradeable].where(mask)`),
which is correct for SIGNALS (regressions, industry factor). But the SAME masked frame is passed to
`run_backtest`, where `gross = (weights.shift(1) * returns).sum(axis=1)` skips NaN. So when a held
name leaves the universe on day t, the P&L of the position held from t-1 is silently DROPPED. Exit-day
gains and losses vanish.

Fix:
- Keep `tradeable_returns` (masked) for signal construction only.
- Return the UNMASKED `returns[tradeable]` under a distinct key (e.g. `"valuation_returns"`) and pass
  that to `run_backtest` everywhere, including the walk-forward and every runner path.
- Keep both keys explicit, so they can't be confused again.

Tests, each failing on the current HEAD (prove it in /tmp):
- **End to end:** a name held at t-1 that leaves the universe at t, with a valid close at t. Day-t
  gross P&L includes `w[t-1] * r[t]`, with the exact number asserted.
- A name with a genuinely missing close at t still contributes 0, with no fabricated return.
- Signals are unchanged by the fix: s-scores and positions are identical before and after.

Add `CHANGELOG[10]`. Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh` or `strategies/results/`. Write
`.agents/mimo/VERDICT-strategy-round11.md`. Claude reruns live as r10.
