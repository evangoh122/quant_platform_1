# VERDICT rag-kg round 7
Checker: Claude Sonnet subagent (DeepSeek out of credit)
Range: 2a3029d..64187aa
**Verdict: CHANGES_REQUESTED** (production code correct; two test-strength gaps against explicit request items)

## Findings
1. (blocking) tests/rag/test_sec_knowledge_graph.py:2299-2309 -- test (b) does NOT assert order. The loop over write_calls ends in `pass`; the validate marker lives in a separate `call_order` list and is never compared with write_spy.calls. The final asserts only check validate was called and write_count > 0. Request item 1(b) required "validation recorded before the first write". Fix: have the tracking wrapper record into write_spy.calls (kind "validate") and assert its index is below the first write/createDataFrame/sql index.
2. (blocking) tests/rag/test_sec_knowledge_graph.py:2375-2415 -- schema test checks only field count (9) and column names. Types (INT vs bigint, MAP<STRING,INT>, TIMESTAMP, nullability) are never asserted, though request item 2 required "9 documented columns and types". Reverting IntegerType to LongType in pipelines/build_sec_knowledge_graph.py:236-246 would still pass. The fake _MapType (:~2105) also drops valueContainsNull. Fix: assert dataType per field.
3. (non-blocking) Test (a) injects the undocumented reason by monkeypatching build_graph (:2220-2225). It still imports and calls the real pipeline build(), and asserts ValueError plus zero create/write/sql calls (:2235-2243). Acceptable.
4. (info) Test (c) (:2311-2373) asserts exact values: accepted 2, rejected 0, node 4, edge 3, input map {company:1, filing:1}, empty reasons. Good. Production schema at pipelines/build_sec_knowledge_graph.py:236-246 matches docs/DATA_SCHEMAS.md:498-507 (9 cols, INT, MAP<STRING,INT>) and the DDL at :219-229.
5. (info) The two old vacuous tests (test_pipeline_raises_on_undocumented_reason, test_pipeline_writes_on_documented_reasons) were removed. This was the only test deletion in `git diff 2a3029d..64187aa -- tests` (23 removed lines). They were replaced by 4 real tests, as the request allowed.

## Counts
- python3 -m pytest tests/rag -q: 392 passed, 19 skipped, 0 failed.
- pyspark hidden (PYTHONPATH=nps shim): 392 passed, 19 skipped, 0 failed.
- TestPipelineValidation: 4 passed in both modes, none skipped, none deselected (the "13 deselected" in MiMo's run came from its own env, not reproducible here).
- MiMo's "8 failed psycopg" did not reproduce. There are no failures to compare against b8efa75, so the "pre-existing" claim is moot in this environment.

## Mutation proofs (copies /tmp/kg7-mut-A, /tmp/kg7-mut-B)
- A: replaced validate_and_raise(...) (pipeline :103) with a plain dict -> 2 FAILED (test_undocumented_rejection_raises_and_no_writes: DID NOT RAISE; test_documented_reasons_writes_after_validation: never called). MiMo claimed 3; test (c) passes under my equivalent dict.
- B: moved the call after the table writes (before the manifest Row import) -> 1 FAILED (test (a) only). Test (b) passes, confirming finding 1: the order check is dead code.
