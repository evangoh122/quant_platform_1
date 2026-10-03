# BUILD: strategy round 5b, results header (MiMo)

`strategies/run_residual_reversion.py` hard-codes the results heading ("round 3") and the
"What changed vs r2" table. Claude reran it live after round 5 with
`--output strategies/results/residual_reversion_r4.md`, and the r4 file says "round 3".

Fix:
- Add a `--round` argument (int). Derive it from the `--output` filename `_r<N>.md` when not given.
- Use it in the title and the changelog heading ("What changed vs r<N-1>").
- Move the changelog rows into a dict keyed by round. Add the round 4 rows: the four round-5 fixes
  (NaN validity mask with min_obs; reductions never ADV-capped plus forward-filled ADV; full 60-row
  median window; full 50-row SMA window), each with its files and rationale.
- Change the `--output` default to r4.
- Do NOT edit `strategies/results/residual_reversion_r4.md` by hand. Claude regenerates it live.

Add a test for the round parsing. `python3 -m pytest -q tests/strategies` must pass. LF only,
don't touch `.agents/dispatch.sh`. Commit. Write `.agents/mimo/VERDICT-strategy-round5b.md`.
