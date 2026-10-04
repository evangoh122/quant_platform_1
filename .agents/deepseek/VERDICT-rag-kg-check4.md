Checker: Claude Sonnet subagent (DeepSeek out of credit)

===VERDICT START===
# VERDICT: rag-kg (re-check, round 4)
**Status:** CHANGES_REQUESTED
**Round:** 4

The production code fix is correct and the round-3 blocker is resolved. The only blocker is that the new tests fail when pyspark is hidden, which was an explicit requirement.

## Blocking findings

- [tests/rag/test_sec_knowledge_graph.py:1536 (`_patch_pyspark`), affects tests at ~1617-1670]
  `_patch_pyspark` runs `import pyspark.sql.functions as F_mod` and monkeypatches attributes on the real module. With pyspark hidden (sitecustomize setting `sys.modules["pyspark"]`, `["pyspark.sql"]` and `["pyspark.sql.functions"]` to None), this raises `ModuleNotFoundError`.
  Failing tests: `test_spark_store_parses_provenance_struct`, `test_get_fact_utc_accepted_ts`, `test_facts_timeseries_pit_filter`, `test_neighbors_returns_utc_timestamps`.
  Result: 4 failed in the KG file, and the full suite fails with 4 failed / 647 passed. CI environments without pyspark (databricks-connect is mutually exclusive with pyspark) go red, and the round-3 requirement that the tests pass with pyspark hidden is broken.
  Fix: do not import real pyspark. Build a fake module tree and register it with `monkeypatch.setitem(sys.modules, "pyspark", fake_pkg)`, `"pyspark.sql"` (with a `functions` attribute) and `"pyspark.sql.functions"`.
  The fake `functions` module needs `col`, `transform`, `unix_timestamp` and `struct`. The store's local `from pyspark.sql import functions as F` then resolves to the fake in both environments.

## Non-blocking notes

- `test_neighbors_returns_utc_timestamps` is vacuous. It queries `["FILED"]`, but the fixture contains no `Filing` rows, so no `FILED` edge exists. The result is `[]`, the `for n in neighbors` loop never runs, and nothing is asserted.
  I called `kg.neighbors(company_id, ["REPORTED_FACT"], as_of)` manually through the real `SparkGraphStore` with the fake naive UTC+8 rows. It returned one correct edge with `valid_from` and `accepted_ts` equal to `2023-11-14T22:13:20+00:00`. With `as_of` in 2020 it returned `[]`.
  So the code is correct, but the test should use `REPORTED_FACT`/`INSTANCE_OF` and assert non-empty results and exact values.
- The fake `unix_timestamp`/`alias`/`transform` are no-ops, and the fake DataFrame ignores `select`. The tests therefore prove that the Python side reads `*_epoch` fields and ignores the naive fields (a naive read would crash). They do not prove the Spark expressions themselves, such as `F.transform` with a lambda returning `F.struct`.
  That is acceptable offline. A live Databricks Connect smoke test is still advisable before relying on the Delta path.
- `unix_timestamp(timestamp_col)` is independent of the session timezone, so the epoch approach is sound. The PIT filter in `get_edges_for_node` uses `valid_from_epoch <= int(as_of.timestamp())`, which is consistent.
- `_QuerySecFactsInput` validates ticker via `normalize_symbol` (an injection ticker raises `ValidationError`). `metric` and `period` are free non-blank strings.
  They are only used for in-memory matching (no SQL or prompt interpolation), and output is tagged `content_type="untrusted_tool_data"`, so this is acceptable. Consider a metric charset allowlist as defence in depth.
- Carried over from check3 (unchanged, still non-blocking):
  - no `Filing` entity rows means no `FILED`/`HAS_SECTION`/`HAS_CHUNK` edges in the offline build;
  - the matcher recall for chunk-level citations is about 0 (chunk=0, which is honest);
  - the ontology identity keys differ.

## Checks run

- Timestamp read path (`api/services/sec_knowledge_graph.py` lines 172-318). All four `SparkGraphStore` methods (`iter_nodes`, `iter_edges`, `get_node`, `get_edges_for_node`) read `F.unix_timestamp(...)` for top-level `valid_from`/`accepted_ts` and inside `F.transform` over the provenance struct array (`accepted_epoch`). They build aware UTC datetimes with `datetime.fromtimestamp(int(epoch), tz=timezone.utc)`. No naive datetime reaches `ensure_utc` (the only `ensure_utc` calls on this path are on caller-supplied `as_of`). `.replace(tzinfo=...)` is not used. **pass**
- Real `SparkGraphStore` with fake naive UTC+8 rows and correct epochs: `get_fact`, `facts_timeseries` (pre-2020 gives `[]`, 2024 gives 1 result) and `neighbors` (manual `REPORTED_FACT` check) return correct UTC values with PIT filtering. **pass** (with real pyspark importable)
- `python3 -m pytest -q -p no:cacheprovider tests/rag` -> **pass** (382 passed, 19 skipped)
- KG and agent-tool tests under `TZ=Asia/Singapore` and `TZ=America/New_York` -> **pass** (84 passed each)
- Full suite, `--ignore=tests/lakebase` -> **pass** (661 passed, 67 skipped, 128 s)
- pyspark hidden, KG tests -> **FAIL** (4 failed, 80 passed; blocking finding above)
- pyspark hidden, full suite -> **FAIL** (4 failed, 647 passed, 77 skipped)
- Offline build (jsonl) -> **pass**. 63,520 nodes / 136,786 edges. Manifest: `rejected_rows` 0, `rejection_reasons` {}, `input_rows_by_entity_type` exact (company 2,767 / event 1,741 / risk_factor 1,457 / xbrl_fact 43,722).
- XbrlFact count 43,722, so instant-period facts are retained. `citation_level` is filing for all 43,722 (chunk 0, so no false chunk citations). **pass**
- Idempotency: two builds give byte-identical nodes and edges jsonl. **pass**
- Targeted tests (inject / reject / restatement / supersede / stable / PIT) -> 55 passed. These cover PIT, restatement supersession, stable IDs, exact rejection stats, and the build failing on unknown reasons.
- `query_sec_facts`: ticker injection (`NVDA'; DROP TABLE x;--`) raises `ValidationError`. `extra=forbid` and the naive/str/int `as_of` rejections are covered by passing tests. Output is tagged `content_type=untrusted_tool_data`. **pass**
===VERDICT END===
