# REVIEW: SEC RAG coverage lane (reviewer: Codex gpt-5.6-sol)

Independent REVIEWER after DeepSeek approved round 7 (.agents/deepseek/VERDICT-rag-coverage-round7.md). Do NOT edit repo files; mutation proofs
in /tmp copies. Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered
findings with file:line, counts, mutation results.

Scope: branch slice/rag-coverage vs origin/main — pipelines/sec_rag_ingest.py (ticker→CIK mapping, EDGAR client, in-flight coalescing,
parallel embeddings, Spark adapters/writers, sec_ingest_log, sec_cik_mapping_log, accession ownership), gold/07_gold_sec_coverage.sql,
notebooks/02_ingest_sec_edgar.py (thin wrapper), xbrl_client.py, config/settings.py, resources/jobs.yml, docs (DATA_SCHEMAS.md,
SEC_RAG_COVERAGE_RUNBOOK.md), tests/rag. Spec: .agents/requests/BUILD-rag-coverage.md.
Context: this lane is about to be used for a batched live rollout from 16 tickers to the 300-symbol (then 557) universe: dry-run → 10 → 50 →
rest. Review it as if it will run unattended against SEC EDGAR.
Review for:
1. SEC fair-access compliance: User-Agent fail-closed (no placeholders), request rate ≤ 10/s across ALL threads/workers (global limiter, not
   per-thread), backoff on 429/503, no unbounded retries.
2. Idempotency & resume: re-running a batch doesn't duplicate filings/chunks/embeddings; run_id / checkpoint semantics; partial failures
   recorded in sec_ingest_log and retried; accession ownership conflicts raise.
3. Point-in-time: accepted_ts parsed as UTC (watch naive datetimes from Spark in client tz UTC+8); information_available_ts = accepted_ts.
4. ETFs and non-SEC symbols in the universe (SPY, QQQ, leveraged ETFs, ADRs): mapped/missing handling — no crash, no wrong CIK.
5. Embedding throughput: real parallelism, bounded memory, model loaded once.
6. Run 3 mutations of your own.
Run: python3 -m pytest tests/rag tests/bronze -q (note: your sandbox may block sockets; report which failures are sandbox-only).
