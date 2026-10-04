# BUILD nl1 round 18 (builder: MiMo) — revert the semantic change; fix it in the test shim

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Descriptive commits. NEVER delete or weaken tests.
DeepSeek verdict: .agents/deepseek/VERDICT-nl1-round17.md (2 blocking). RULE: never change PRODUCTION view semantics to make a test pass.

1 (High). Revert in docs/NL1_PROPOSED_SERVING_VIEWS.md: remove `COALESCE(return_1d, 0)` (:432) and `COALESCE(bench_return, 0)` (:459) and restore
   `WHERE return_1d IS NOT NULL` / `WHERE bench_return IS NOT NULL` (were :441, :466) — masked/NULL returns are data-quality breaks, excluded and
   disclosed, never interpolated (contract :13-14, :709). Remove the false comment at :424-425. The DuckDB-only eager `LN(0)` error belongs in the
   `to_duckdb()` shim: rewrite `LN(1 + <col>)` → `LN(GREATEST(1 + <col>, 1e-10))` IN THE SHIM ONLY (documented as a DuckDB evaluation-order
   workaround; production keeps its CASE/NULL semantics). Tests: (a) a −100% day → cumulative NULL + status invalid_return; (b) a masked NULL day is
   EXCLUDED (no output row for it / not counted as 0%) and the window's status/coverage reflects it as documented. Mutation: re-add COALESCE(...,0)
   in the DOC → test (b) FAILS.
2 (Medium). Adjusted-mode momentum ordering: the LAG-before-null-filter test only checks the fallback variant. Add the same test for the ADJUSTED
   variant (extract_view_sql(..., variant="adjusted")). Mutation: add `WHERE return_1d IS NOT NULL` to the adjusted with_momentum (:198) → FAILS.
Prove each mutation by editing the DOC in a copy made with `git archive HEAD | tar -x -C /tmp/<dir>`; paste outputs.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps);
python3 -m analytics_nl.export_schemas --check. .agents/mimo/VERDICT-nl1-round18.md. Commit everything.
