# CHECK: rag-coverage round 8a (checker: DeepSeek)

Read-only. Mutation proofs in /tmp copies (cp -r to /tmp/rc8a-mut-*). Write .agents/deepseek/VERDICT-rag-coverage-round8a.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-rag-coverage-round8a.md (findings 1–6 of Codex .agents/codex/VERDICT-rag-coverage-review.md). Commit 75d6adc.
For each of the 6 items, verify the fix AND that its test FAILS on the old code (revert that one fix in a /tmp copy). Rerun Codex's probes:
1. bronze write: explicit StructType incl. typed null raw_payload; Delta MERGE keyed on accession (not append); re-run → 0 inserted; ownership
   conflict inside the MERGE path; actual inserted count.
2. UTC: under TZ=Asia/Singapore + time.tzset(), 2025-02-20T18:30:00Z → 1740076200 in what's handed to Spark.
3. Discovery: exhausted submissions → failure recorded, not "0 filings success"; history overlap uses filingFrom/filingTo; missing
   acceptanceDateTime recorded as skipped with reason.
4. CIK: two-CIK fixture → ambiguous; network failure + 30-day cache → cache used; dry run doesn't write the cache. `ambiguous` documented in
   docs/DATA_SCHEMAS.md.
5. ONE process-wide limiter shared by sec_rag_ingest AND xbrl_client (two clients in parallel threads → ≤ 10 per 1-s window); HTTP-date Retry-After.
6. max_workers actually used; in_progress persisted before work; attempt increments from the log; resume skips succeeded; ownership conflict
   recorded as failed.
No tests deleted/weakened (git diff 640f64e..HEAD -- tests). Out of scope this round: build_sec_embeddings.py, hybrid_retriever.py, gold/07,
tools_retrieval.py (round 8b) — flag if they were touched.
Run: python3 -m pytest tests/rag tests/bronze -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps tests/rag.
