===CODEX VERDICT START===

CHANGES_REQUESTED

Blocking finding:

- The production build does not fail on undocumented rejection reasons. `build_graph()` returns `stats` at [pipelines/build_sec_knowledge_graph.py:94](/home/jianj/code/qp1-kg/pipelines/build_sec_knowledge_graph.py:94), but the pipeline proceeds directly to table creation/writes without calling `validate_rejection_reasons()`. The validator merely returns unknown reasons at [sec_kg/build.py:865](/home/jianj/code/qp1-kg/sec_kg/build.py:865). Independent proof produced `UNKNOWN_VALIDATION ['totally_unknown_reason:x']` and `PIPELINE_CALLS_VALIDATOR False`. Exact rejection statistics are also not emitted by the production build.

Validated:

- Checker `check5`: `APPROVED`.
- Test suite: `382 passed, 19 skipped` in 95.70s.
- Full offline build: exactly `43,722` `XbrlFact` nodes; `32,143` duration and `11,579` instant; zero duplicate node IDs and zero rejections.
- PIT/restatements: provenance and edge filtering occurs before selection at [sec_knowledge_graph.py:385](/home/jianj/code/qp1-kg/api/services/sec_knowledge_graph.py:385); latest eligible version selection is at line 403; supersession handling is at [sec_kg/build.py:626](/home/jianj/code/qp1-kg/sec_kg/build.py:626). All edges had `valid_from == accepted_ts`.
- Instant/duration identities include `period_start`, preventing collision: [sec_kg/model.py:183](/home/jianj/code/qp1-kg/sec_kg/model.py:183).
- Citations are conservatively verified at [sec_kg/build.py:187](/home/jianj/code/qp1-kg/sec_kg/build.py:187); filing fallback adds `source_url` at line 571. Query results expose both fields at [sec_knowledge_graph.py:448](/home/jianj/code/qp1-kg/api/services/sec_knowledge_graph.py:448).
- Timestamp conversion uses epoch → aware UTC at [sec_knowledge_graph.py:223](/home/jianj/code/qp1-kg/api/services/sec_knowledge_graph.py:223). Existing exact-value checks cover facts/timeseries, but a `/tmp` mutation adding 28,800 seconds specifically to neighbor edge reads still passed the neighbor test. This remains a non-blocking test gap.
- Tool validation uses `extra="forbid"` and typed validators at [tools_retrieval.py:220](/home/jianj/code/qp1-kg/agent/tools_retrieval.py:220); output is isolated as `untrusted_tool_data` at line 281.
- Node and edge vocabularies exactly matched `origin/slice/ontology-update:ontology/knowledge_graph.yaml`.

===CODEX VERDICT END===
