# CHECK: options-right-case round 2 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies (cp -r to /tmp/optcase2-mut-*). Write .agents/deepseek/VERDICT-options-right-case-round2.md
between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts,
mutation results. MiMo's self-verdict is not evidence.

Build request: .agents/requests/BUILD-options-right-case-round2.md. Previous checker verdict: .agents/deepseek/VERDICT-options-right-case.md.
Commits: c3a844a..HEAD.
Verify:
1. QUOTES path (_right_from_contract_type → shape_quote_row) emits lowercase 'call'/'put' again; DAY path emits 'PUT'/'CALL';
   a test asserts both. Mutation: make the quotes path uppercase → test FAILS.
2. DuckDB semantic test extracts the `day` CTE from gold/02 at test time (no retyped copy); only the documented shims
   (availability expression literal, universe fixture). IMPORTANT: MiMo reported "12 skipped (DuckDB-removal skips)" — check
   whether the DuckDB tests SKIP when duckdb is missing. In this environment duckdb is installed (python3 -c "import duckdb");
   confirm the DuckDB tests actually RUN (not skipped) here and fail when one UPPER in gold/02 is reverted. CI installs duckdb
   (.github/workflows/ci.yml) — confirm.
3. Repo-wide case-sensitivity scan covers .py (pipelines/, ml/, strategies/, api/, analytics_nl/, notebooks/) and silver/gold/pipelines
   .sql, excluding tests/ and .agents/; plant `WHERE right = 'PUT'` in a non-test .py in a /tmp copy → FAILS.
4. Maintenance SQL: backtick-quoted `right`, trailing newline, idempotent, before/after verification SELECTs, header notes the
   one-off exception to docs/BRONZE_REFRESH_PLAN.md:13.
5. The tautological test_mutation_proof_revert_upper_fails was removed (allowed) — no other test removed/weakened (git diff c3a844a..HEAD -- tests).
Run: python3 -m pytest -q tests/gold tests/bronze tests/silver (pre-existing pytz ModuleNotFoundError failures are known; list them);
pyspark hidden: PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps same.
