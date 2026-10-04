# CHECK: corporate-actions round 7, Massive-only (checker: DeepSeek)

Read-only for source. No network, no secrets. Mutation proofs in /tmp copies (cp -r to /tmp/ca7-mut-*). Write
.agents/deepseek/VERDICT-corporate-actions-round7.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", numbered findings with file:line, counts, mutation results. MiMo's self-verdict is not evidence.

Owner decision: Massive ONLY (no yfinance anywhere in the adjustment path). Build request:
.agents/requests/BUILD-corporate-actions-round7-massive-only.md. Commits: 294bc37..HEAD.
Verify:
1. No yfinance in the pipeline (grep the repo excluding tests/.agents/docs history notes); requirements: is yfinance still listed and used
   elsewhere? duckdb in requirements.
2. Massive adapter intact: pagination (next_url + apiKey), bounded retry 429/5xx, 401/403 raise without key, exact-ticker filter,
   ratio = split_to/split_from, key redaction `raise ... from None`, notebook-boundary redaction. Key-leak tests still exercise real code.
3. silver/08: `_massive_splits` WHERE source='massive', deduped to one row per (symbol, ex_date) by latest fetched_ts; other sources IGNORED;
   price-jump data_quality_breaks retained with explicit columns; all INSERT/MERGE explicit columns.
4. Real-SQL DuckDB tests extract SQL from silver/08 at test time (no retyped SQL). Cases: AMZN 20:1 → factor 20 and ≈+2% continuity;
   duplicate massive rows → factor 20 not 400; SQQQ 0.2; yfinance row ignored; unexplained −50% → one break row; matching split day → none.
   Mutations: remove dedupe → FAILS; drop the source filter → FAILS; remove the price-jump break logic → FAILS.
5. 17 yfinance-only tests were removed — confirm each was yfinance/dual-source-only (allowed) and no Massive/silver/security test was removed
   or weakened: git diff 294bc37..HEAD -- tests.
Run: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py (5 pre-existing COT TestComputeReleaseTs pytz failures known);
pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps same. LF endings on changed files.
