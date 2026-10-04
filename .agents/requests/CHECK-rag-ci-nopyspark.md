# CHECK: rag CI no-pyspark test fix (DeepSeek)

Read-only. Review the last MiMo commit "fix(tests): add fake_pyspark fixture" (`tests/rag/conftest.py`,
`tests/rag/test_hybrid_retriever.py`). Write `.agents/deepseek/VERDICT-rag-ci-nopyspark-check.md`
(===VERDICT START/END===, Status APPROVED or CHANGES_REQUESTED).

1. Production code unchanged? (`git diff HEAD~3 -- agent api pipelines` must be empty.)
2. Does the fake `pyspark.sql.functions` stub still make the 8 tests verify real behaviour?
   It must not make every filter pass trivially. Prove it with mutations in /tmp, run under a
   sitecustomize that sets `sys.modules[...] = None` for pyspark:
   - Remove the fallback `as_of` filter.
   - Remove the `unix_timestamp` epoch in `_load_corpus`.
   - Break the idempotency anti-join in `build_sec_embeddings`.
   Each must fail at least one test.
3. When real pyspark IS installed, does the fixture leak? It must not break other test
   modules, or tests that use real pyspark. Run `python3 -m pytest -q tests`.
