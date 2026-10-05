# REVIEW: rag-coverage — merge of origin/main + Apps warehouse fallback + repair nits (reviewer: Codex)

Branch slice/rag-coverage (PR #28). Your previous review approved rounds 19/19b/19c (.agents/codex/VERDICT-rag-coverage-round19c.md).
New since then: 5c1d6c2 (merge origin/main incl. #37 — Databricks Apps have no Spark, so SEC retrieval falls back to the SQL warehouse; conflict
in api/services/hybrid_retriever.py resolved by keeping this branch's per-ticker corpus and adding the fallback to every Spark read), ff24521
(repair_cik_ownership: one UPDATE per filing, filing_url rewrite), efa3446 (fallback tests; missing gold_sec_coverage → NoCoverageError).
DeepSeek APPROVED: .agents/deepseek/VERDICT-rag-coverage-merge-main.md (note its non-blocking items: cosmetic "mutation" tests, no test for the
legacy `_load_corpus` fallback). Claude live (WSL, Spark forced off): NVDA 894 chunks / 894 embeddings via the warehouse.
Your sandbox has no network: run `python3 -m pytest tests/api tests/agent tests/rag -q` (warehouse/Databricks calls must be faked; a hang on
SDK metadata retries is a sandbox limit, report it as such). Mutation proofs only in /tmp via `git archive HEAD | tar -x -C /tmp/<dir>`.
Focus: nothing from #37 lost; no user values in SQL; startup warm-up cannot crash the app when gold_sec_coverage is absent; per-ticker cache
bounded. Decide whether DeepSeek's non-blocking notes must be fixed before merge. Print the verdict between ===VERDICT START=== /
===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line. Do not edit files.
