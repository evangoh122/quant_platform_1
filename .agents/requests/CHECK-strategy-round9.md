# CHECK: strategy round 9 (DeepSeek)

Commit "fix(strategy): round 9" fixes CI and CodeRabbit's findings on #16 (see
`.agents/requests/BUILD-strategy-round9.md`). Read-only. Write
`.agents/deepseek/VERDICT-strategy-check7.md` (===VERDICT START/END===, Status).

Claude's checks:
- Under pandas 3.0.6, the pre-round-9 code fails 10 tests and round 9 passes all 47.
- r8 (live) is IDENTICAL to r7 to 3 decimals: net −0.382, OOS −0.636, DSR 0.

Verify:
1. Every `.to_numpy()` / `.values` that is later written to is now a copy. Audit `strategies/` and `ml/`.
2. ADV is forward-filled per symbol from past values only, then zero-filled only for names never
   seen, and the SAME frame feeds both the cap and the costs.
3. **Is r8 == r7 plausible?** Using the code paths (synthetic replay, or reasoning about when a held
   name leaves the universe with NaN ADV), estimate how often the old zero-fill actually bit. If the
   fix never runs, the tests should still prove the behaviour. Do they?
4. The test-path fixes work from any cwd.

Run `python3 -m pytest -q tests/strategies tests/ml`, and the same suite with pyspark hidden.
