# BUILD: NL1 round 3 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each fix. NEVER delete or weaken
> existing tests, EXCEPT replacing the vacuous ones named below (list them).

DeepSeek (`.agents/deepseek/VERDICT-nl1-contracts.md`, read it fully) found 4 blocking issues:

1. **`SELECT *` in the proposed DDL** (`docs/NL1_PROPOSED_SERVING_VIEWS.md:~100-111`, in the
   `with_vol` / `with_drawdown` CTEs). Enumerate every column explicitly in every stage of every
   view.
2. **The `SELECT *` test is vacuous** (`tests/analytics_nl/test_ddl.py:~45-59`; the OR-of-negations
   only fails if both appear on one line). Replace it with a whitespace- and newline-insensitive
   check: normalise the SQL (strip comments, collapse whitespace), then regex `\bSELECT\s+\*` and
   `\.\*`. Prove in /tmp that the current DDL FAILS it.
3. **Silver bounds are never tested** at the classification level (`tests/analytics_nl/test_policy.py:~274-287`
   tests a Gold entry and asserts a tautology). Add boundary tests on a real Silver entry:
   - exactly 2 years vs 2 years + 1 day;
   - 10 tickers vs 11;
   - 10,000 rows vs 10,001;
   - missing entity/date scope.

   Each just-over case must REJECT, and REJECT must emit no SQL.
4. **No registry entry is `layer: silver`**, so the Silver path is unreachable. Register at least one
   real Silver drill-down pair per the plan: e.g. `price.trend` and `volume.trend` at daily-bar
   granularity for ≤10 named tickers over ≤2 years, served from a bounded Silver serving view over
   `silver_ohlcv` or `bronze_ohlcv_day`. Add its DDL to the appendix (explicit columns,
   `information_available_ts` filter). Gold aggregates stay as they are. Document in the registry
   which questions route to Silver vs Gold.

Fix any quick factual non-blocking notes too. Regenerate the schemas if the models change, and keep
the sync test green. Run `python3 -m pytest -q tests/analytics_nl` and the full suite with
`--ignore=tests/lakebase`. LF line endings only. Don't touch `.agents/dispatch.sh`. Update
`.agents/mimo/VERDICT-nl1-contracts.md` (round 3).
