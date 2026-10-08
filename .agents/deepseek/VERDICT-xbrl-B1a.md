===VERDICT START===
# VERDICT: xbrl-B1a — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 1

## Summary

Reviewed commits `3983aed..762ca56` (`feat/xbrl` pipeline + tests + jobs.yml) against
`BUILD-xbrl-B1a.md` and Plan B §2.1/§2.2/§2.5. Baseline is green (34/34 focused tests,
2469 passed offline). Two named mutation requirements are not met: the
"overwrite instead of append" mutation is caught by **no** test, and the required
"same-payload skip within a run" test is a no-op stub with zero assertions.

## Blocking findings

1. **[pipelines/ingest_sec_companyfacts.py:603,665] — "overwrite instead of append"
   mutation is not caught by any test.** The bronze (and manifest) writes use
   `df.write.mode("append").saveAsTable(table)`, but no shipped test inspects the Spark
   write mode. The test doubles `_make_delta_writer` / `_make_manifest_writer`
   (`tests/bronze/test_sec_companyfacts.py:260-267`) only collect row dicts, never touch
   `SparkCompanyFactsWriter`. Running the mutation (`mode("append")` → `mode("overwrite")`)
   in a `git archive HEAD` copy still yields **34 passed**. This violates BUILD item 4
   ("mutations to run and paste FAILED output for … overwrite instead of append") and
   Plan B §2.5 ("The tests must catch each mutation"). Failure scenario: a future refactor
   flips the write mode to overwrite and silently destroys prior bronze observations with
   no red test.

2. **[tests/bronze/test_sec_companyfacts.py:635] — `test_same_payload_skipped_within_run`
   asserts nothing (no-op stub).** The body monkeypatches `_resolve_user_agent`/
   `_validate_user_agent`, calls `run_ingest_companyfacts`, and ends with a comment
   "Let's just test with the direct approach" — no `assert`, and it does not even reach a
   successful fetch (the single fake response is a company-facts payload, not
   `company_tickers.json`, so `build_cik_map` marks AAPL missing and nothing is fetched).
   The required "skip writing when the same (cik, payload_hash) was already written in
   this run" behaviour (BUILD item 2/4, Plan B 2.5 item 2) is therefore untested; removing
   the skip logic in `run_ingest_companyfacts` (`:442-451`) would not fail any test.

## Item-by-item

- **Item 1 (four named mutations) — PARTIAL.** Verified independently in `/tmp` archive
  copies (see table below). Three of four fail as required; "overwrite instead of append"
  does not.
- **Item 2 (bronze columns / `ingested_at` / append / create-if-absent) — PASS.** The 25
  columns in `BRONZE_FACT_COLUMNS` (`:64-90`) and the `CREATE TABLE IF NOT EXISTS` DDL
  (`:562-588`) match Plan B §2.2 exactly (order and names). `ingested_at` is set from
  `datetime.now(timezone.utc)` at run start (`:425`) and never derived from a filing
  timestamp. Write mode is `append` (`:603`); table is created if absent (`:710-711`).
- **Item 3 (rate limit / Retry-After / retries / timeouts / logging) — PASS.** Process-wide
  singleton `get_global_limiter` (thread-safe, clamps to `min(max_rps, 10)`) is reused,
  not per-thread (`sec_rag_ingest.py:70-83`). `SecClient._request` honours `Retry-After`
  via `_parse_retry_after` + `trigger_cooldown`, caps at 120 s, bounded retries
  (`max_retries=5`), 30 s timeout. Grep of logger calls shows no response body and no
  contact email is logged; `_resolve_user_agent` logs only the source, never the value.
  `test_no_email_in_logs` (`:776`) asserts this.
- **Item 4 (Spark vs Python parsing) — NON-BLOCKING deviation.** Flattening is pure Python
  on the driver (`flatten_company_facts` → list of dicts → `spark.createDataFrame`), not a
  Spark transformation as §2.1 literally requires. For B1a payload sizes (NVDA
  companyfacts ≈ several MB → tens of thousands of rows) this is memory-safe (per-CIK, not
  accumulated) and acceptable. Recommend reconciling to a Spark transformation (or an
  explicit coordinator sign-off) before the 557-ticker rollout in the silver/gold slices.
- **Item 5 (jobs.yml / bundle-sync tests) — PASS.** `sec_companyfacts_ingest` job carries
  catalog/schema params and the same secret scope/key as `sec_rag_ingest`
  (`evangoh_capstone` / `sec_edgar_user_agent`), placed before `sec_knowledge_graph_build`
  (`resources/jobs.yml:95-115`). The entrypoint→job mapping was added to
  `TestJobEntrypointImportsN5::test_all_entrypoint_imports_declared`
  (`tests/rag/test_sec_embeddings_incremental.py:770`) — a real AST-driven dependency
  check, not a weakening. `test_bundle_sync.py` / `test_check_schema_contract.py` do not
  enumerate jobs or tables, so no update was required there. There is no cross-job
  `depends_on` to `silver_gold_refresh`, but the silver/gold XBRL transform does not exist
  yet (B1 part b), so positional ordering is all that is expressible now.
- **Item 6 (offline suite) — PASS.** `python3 -m pytest -q -m "not spark and not lakebase
  and not databricks"` → **2469 passed, 107 skipped, 24 deselected** (249.7 s).

## Mutation verification (independent `git archive HEAD` copies under /tmp)

| Mutation | Applied to | Test | Result |
|---|---|---|---|
| accept placeholder UA (`_placeholder_re.search` → `False`, sec_rag_ingest.py:172) | mut1 | `TestUserAgentValidation::test_reject_placeholder_email`, `test_reject_your_email_placeholder`, `TestMutationProofs::test_mutation_accept_placeholder_ua` | **3 failed** |
| remove rate limiter (`self._limiter.acquire()` → `pass`, sec_rag_ingest.py:821) | mut2 | `TestSecClientCompanyFacts::test_rate_cap_respected` | **1 failed** (`assert 1000.0 > 1000.0`) |
| overwrite instead of append (`mode("append")` → `mode("overwrite")`, both `:603`,`:665`) | mut3 | (none) | **0 failed — 34 passed** |
| drop malformed facts (skip rows with `value_decimal is None`) | mut4 | `test_flatten_malformed_value_decimal_is_none`, `test_mutation_malformed_fact_not_dropped` | **2 failed** |

## Non-blocking notes

- **[pipelines/ingest_sec_companyfacts.py:427]** The ingest loop is sequential — no
  bounded concurrency (`ThreadPoolExecutor`). Safe (≤10 req/s trivially holds), but the
  §2.1 "bounded concurrency" intent is not implemented.
- **[pipelines/ingest_sec_companyfacts.py:466,266]** Manifest `attempt_count` is hardcoded
  `1` on success and left at the default `1` on failure; the real retry/attempt count from
  `SecClient._request_count/_retry_count` is not plumbed through. Plan B §2.1 asks for an
  accurate attempt count.
- **[tests/bronze/test_sec_companyfacts.py:498]** `test_retry_after_honoured_on_429` first
  constructs `SecClient(..., limiter=clock)` (passing the fake clock as the limiter) and
  immediately rebuilds it correctly at `:502`; the first construction is dead code.
- **`BRONZE_FACT_COLUMNS` (`:64`) is defined but never used** to enforce/validate the
  row schema; column correctness is currently guaranteed only by the `_flatten_one_entry`
  dict and the DDL string staying in sync. Consider asserting against it in a test.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **34 passed** (0.28 s)
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py tests/test_bundle_sync.py tests/test_schema_env_override.py tests/test_check_schema_contract.py tests/rag/test_sec_embeddings_incremental.py -q` → **66 passed**
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2469 passed, 107 skipped, 24 deselected** (249.7 s)
- mut1 (placeholder UA) → 3 failed; mut2 (remove limiter) → 1 failed; mut3 (overwrite) → 0 failed; mut4 (drop malformed) → 2 failed
===VERDICT END===
