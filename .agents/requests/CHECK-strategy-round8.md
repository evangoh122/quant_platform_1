# CHECK: strategy round 8 (DeepSeek)

Commit 9b66b39 fixes the four Codex findings in `.agents/codex/VERDICT-strategy-final.md`. Claude
rebuilt `gold_regime_features` live (1,191 rows, z-score from 2023-01-03, BROAD 366 / MIXED 239 /
NARROW 586) and reran as `strategies/results/residual_reversion_r7.md`. Read-only. Write
`.agents/deepseek/VERDICT-strategy-check6.md` (===VERDICT START/END===, Status).

Check, each with a /tmp proof:
1. **Costs on the executed notional.** A large exit is charged in full.
   - Is the participation-based impact (if any) computed on the true participation?
   - Is borrow still charged on shorts?
   - The ADV cap property test still passes.
2. **`universe.py` dense grid.**
   - Codex's sparse case: one absent session → B is not admitted for 5 dates.
   - Dense and sparse inputs agree with the SQL semantics.
   - Is there a calendar-source look-ahead? The calendar must not include future dates relative to
     the decision.
3. **`gold/07` z-score guard** uses `COUNT(rsp_spy_ratio)`. Does the live table agree with the
   numbers above?
4. **Leverage wording** is 50%/50%.
5. **r7.** Internally consistent, the changelog is accurate, and it states no edge. Did the costs
   rise as expected vs r6?

Run:
- `python3 -m pytest -q -p no:cacheprovider tests/strategies tests/ml`;
- the same suite with pyspark hidden.
