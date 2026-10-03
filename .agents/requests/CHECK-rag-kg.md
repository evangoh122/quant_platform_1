# CHECK: SEC knowledge graph (DeepSeek)

Branch `slice/rag-kg`. Spec: `.agents/requests/BUILD-rag-kg.md`. MiMo built:
- `sec_kg/` (model, build, enrichment);
- `api/services/sec_knowledge_graph.py`;
- `pipelines/` and `scripts/build_sec_knowledge_graph.py`;
- `agent/tools_retrieval.py::query_sec_facts`;
- a job in `resources/jobs.yml`;
- 66 tests.

Offline build: 83,598 nodes, 135,805 edges from 49,687 entities (`evals/data/sec_entities.jsonl`,
present locally). Read-only; scratch work in /tmp. Write `.agents/deepseek/VERDICT-rag-kg.md`
(===VERDICT START/END===, Status).

Check, with proofs:
1. **Point-in-time.** No query returns a node, edge or fact with `accepted_ts > as_of`. Restatements:
   a newer filing's value for the same (metric, period, unit) supersedes the older one AS OF its
   acceptance, and both are retained. Build a synthetic restatement and test it at three `as_of`
   dates.
2. **XBRL normalisation.** metric / period_start / period_end / unit / value are parsed correctly:
   instant vs duration periods, units (USD, shares, USD/share), scale/sign.

   Spot-check 10 real facts from `sec_entities.jsonl` against their `source_chunk_id` text.
3. **Stable IDs and idempotency.** The same input gives identical IDs and an identical SHA. No ID
   collisions across tickers or filings.
4. **Provenance.** Every node and edge carries an accession and a `source_chunk_id`, and
   `query_sec_facts` returns them so answers can cite sources.
5. **`query_sec_facts` security.** Strict typed args with `extra=forbid`: an injection string in the
   ticker or metric is rejected. Its output is treated as DATA. This lane must follow
   `docs/SECURITY_PROMPT_INJECTION.md`, which is on branch `slice/chat-security`; read it with
   `git show origin/slice/chat-security:docs/SECURITY_PROMPT_INJECTION.md`.
6. **Ontology alignment.** The ontology lane (branch `slice/ontology-update`, file
   `ontology/knowledge_graph.yaml`) defines 9 deterministic node types and 10 edges, with Segment,
   Product and Customer as optional LLM enrichment. Does `sec_kg/model.py` match exactly? List every
   mismatch.
7. **LLM enrichment.** OFF by default, budget-guarded, and no network in tests.
8. **The Delta job** is unscheduled, and tests pass with pyspark hidden.

Run `python3 -m pytest -q -p no:cacheprovider tests/rag`, and the full suite with
`--ignore=tests/lakebase`.
