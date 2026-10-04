===VERDICT START===

# VERDICT: rag-coverage — Codex review

Status: CHANGES_REQUESTED

DeepSeek round-7 approval was present. The repository remained unmodified.

## Findings

1. **[P1] Bronze writes are neither atomic nor reliably constructible.** [sec_rag_ingest.py:1256](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1256) infers a DataFrame containing an always-null `raw_payload`, which Spark cannot type reliably, then performs a plain append at line 1257. There is no Delta `MERGE`, accession conflict check inside the transaction, or actual inserted-row count. Concurrent runs can duplicate filings.

2. **[P1] `accepted_ts` can shift by eight hours.** [sec_rag_ingest.py:210](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:210) converts UTC timestamps to naïve datetimes before Spark serialization. Installed PySpark serializes naïve timestamps using `time.mktime`; under this UTC+8 client, `2025-02-20T18:30:00Z` became epoch `1740047400` instead of `1740076200`.

3. **[P1] Filing discovery can silently report incomplete coverage as success.** [sec_rag_ingest.py:606](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:606) converts an exhausted submissions request into an empty result; history failures are also silently skipped. History inclusion checks `filingFrom < start_date` instead of whether the file overlaps the cutoff, and `_collect_filings` truncates to the acceptance array length, silently dropping rows whose acceptance value is absent. A synthetic relevant history file after the cutoff produced zero filings and was never fetched.

4. **[P1] CIK ambiguity and cache fallback are not implemented safely.** [sec_rag_ingest.py:337](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:337) overwrites duplicate ticker mappings and can only emit `mapped` or `missing`, never `ambiguous`. A two-CIK fixture mapped silently to the last CIK. The stale fallback at line 840 calls `_try_load_cache(..., ttl=0)`, which rejects every positive-age sidecar; the network-failure probe raised instead of using the valid stale cache. Dry runs can also rewrite the persistent cache before reaching the dry-run branch.

5. **[P1] SEC fair-access behavior remains incomplete.** [sec_rag_ingest.py:971](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:971) creates a limiter per ingestion invocation rather than one process-wide limiter, while [xbrl_client.py:20](/home/jianj/code/qp1-ragcov/api/services/xbrl_client.py:20) maintains another independent limiter. Concurrent paths can exceed the aggregate limit. HTTP-date `Retry-After` values are discarded at [sec_rag_ingest.py:543](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:543); the probe returned `None`.

6. **[P1] Resume and worker semantics are incomplete.** `max_workers` is accepted but never used; filings are processed serially at [sec_rag_ingest.py:1092](/home/jianj/code/qp1-ragcov/pipelines/sec_rag_ingest.py:1092). The `in_progress` entry is not persisted before work, attempt is always `1`, ingest logs are never read for resume, and ownership conflicts are re-raised without recording the failed filing.

7. **[P1] Parallel embedding writes race through one shared temporary view.** Each worker replaces `_embed_src` at [build_sec_embeddings.py:237](/home/jianj/code/qp1-ragcov/pipelines/build_sec_embeddings.py:237) before issuing its MERGE. Concurrent workers can overwrite another batch’s view or conflict on the target table. Returned `rows_written` is candidate count, not actual inserts. Additionally, the runbook supplies a comma-separated pilot list, but line 104 performs scalar ticker equality, so that documented command embeds nothing. The serverless job declares none of the required model dependencies.

8. **[P1] Retrieval still contains an unbounded all-corpus path and a PIT leak.** [hybrid_retriever.py:424](/home/jianj/code/qp1-ragcov/api/services/hybrid_retriever.py:424) collects all chunks and embeddings, and `reload_corpus(None)` eagerly calls it at line 594, defeating the bounded LRU. Dense search at [hybrid_retriever.py:869](/home/jianj/code/qp1-ragcov/api/services/hybrid_retriever.py:869) excludes only parseable future timestamps; null or malformed timestamps remain eligible for cosine scoring.

9. **[P1] Coverage SQL does not honor the target schema or required universe contract.** [07_gold_sec_coverage.sql:10](/home/jianj/code/qp1-ragcov/gold/07_gold_sec_coverage.sql:10) hard-codes the development catalog/schema, while the runner only substitutes date placeholders. Its full outer joins include out-of-universe rows, and its CIK fallback reads bronze filings rather than the latest successful mapping log, leaving mapped zero-filing tickers without their CIK.

10. **[P1] Coverage-table failures can be masked by substring fallback.** [hybrid_retriever.py:417](/home/jianj/code/qp1-ragcov/api/services/hybrid_retriever.py:417) rethrows raw Spark/table errors. These reach the broad handler at [tools_retrieval.py:153](/home/jianj/code/qp1-ragcov/agent/tools_retrieval.py:153), which attempts substring retrieval instead of returning `retrieval_unavailable`.

## Counts and checks

- Diff reviewed: 54 files, 7,166 insertions, 4,383 deletions.
- `python3 -m pytest tests/rag tests/bronze -q`: **583 passed, 36 skipped, 0 failed**.
- No sandbox/socket-only failures.
- `git diff --check origin/main...HEAD`: passed.
- Worktree remained clean.

## Independent mutation results

All three mutations were isolated under `/tmp` and were killed:

1. Allowed an eleventh rate-limiter request: rolling-window test failed with **11 requests**.
2. Removed the PIT upper-bound comparison: future-filing test failed.
3. Disabled accession ownership rejection: conflict test failed because no exception was raised.

Mutation score: **3/3 killed**.

===VERDICT END===
