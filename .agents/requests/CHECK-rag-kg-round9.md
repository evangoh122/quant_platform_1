# CHECK: rag-kg round 9 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies (cp -r to /tmp/kg9-mut-*). Write .agents/deepseek/VERDICT-rag-kg-round9.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered findings with file:line, counts,
mutation results. MiMo's self-verdict is not evidence.

Build request: .agents/requests/BUILD-rag-kg-round9.md (from Codex review .agents/codex/VERDICT-rag-kg-review2.md). Commits: 3a85da8..HEAD.
Verify all 6 items and rerun each requested mutation proof yourself. Pay special attention to:
1. Timestamps: NO `.timestamp()` on a naive datetime anywhere in sec_kg/, pipelines/build_sec_knowledge_graph.py, scripts/,
   api/services/sec_knowledge_graph.py (grep). The TZ=Asia/Singapore test really changes process tz (time.tzset) and would fail on old code.
2. Restatement: facts_timeseries returns exactly one version per (cik, concept, period_start, period_end, unit) — the latest with
   accepted_ts <= as_of; as-of between versions returns the earlier one.
3. Decimal: MiMo says "dual tolerance (relative + absolute)". A tolerance can reintroduce Codex's bug: verify
   9007199254740992 vs 9007199254740993 does NOT match, and state the exact tolerance semantics (does an XBRL value 1000000 match text
   "1.0 million"? does 100 match 101?). Any relative tolerance large enough to match different integers is a finding.
4. Stale rows: `whenNotMatchedBySourceDelete()` — is the delete SCOPED to the rebuilt universe/partitions, or would a partial rebuild
   (subset of tickers) delete every other ticker's graph? A partial rebuild wiping the table is a blocking finding. Check how the build is
   invoked (CLI args for tickers?).
5. Inputs bounded + ticker allow-list enforced before the backend is called (assert backend not called in tests).
6. No driver-wide collect: toLocalIterator is still a full scan to the driver — acceptable for the build only if bounded batches; for
   QUERIES the predicates must be pushed into Spark with a LIMIT before collecting. Verify the query path filters before collecting.
7. No tests deleted/weakened: git diff 3a85da8..HEAD -- tests.
Run: python3 -m pytest tests/rag -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q.
