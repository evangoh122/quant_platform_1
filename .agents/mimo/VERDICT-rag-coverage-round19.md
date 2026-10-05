# VERDICT: rag-coverage round 19 — MiMo
**Status:** APPROVED
**Round:** 19

## Blocking findings
(none)

## Non-blocking notes
- Item 1 (CIK overrides): `load_cik_overrides()` has a `yaml` import at function level. If PyYAML is missing, the function raises `ModuleNotFoundError` at runtime. Acceptable since PyYAML is a project dependency, but worth noting.
- Item 2 (Foreign filers): 20-F section patterns use simplified regex (Item 3.D, 4, 5, 8). Complex 20-F filings with non-standard item numbering may fall back to full-document chunking. This is the intended fallback behavior per the BUILD request.
- Item 5 (xbrl_client): The `test_mutation_old_env_get_fails` test verifies the *semantic difference* between the old buggy code and the correct code, but does not literally revert the production function. The `test_delegates_to_resolve_user_agent` test directly asserts the delegation chain. Together they provide mutation-proof coverage for the round-18 blocker.

## Checks run
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → **177 passed, 6 skipped** (32.03 s)
- `python3 -m pytest tests/rag tests/bronze -q --ignore=tests/rag/test_langgraph_engine.py` → **1147 passed, 50 skipped** (121.78 s)
  - `test_langgraph_engine.py` excluded due to pre-existing `ModuleNotFoundError: No module named 'api.services.rag_engine'` (not related to this round)
- Mutation: `build_cik_map` ignores overrides → `test_mutation_ignore_overrides_fails` catches it (ciks list differs)
- Mutation: `extract_sections` ignores form_type → `test_extract_sections_20f` catches it (20-F sections not found)
- Mutation: runbook loses `--catalog`/`--schema` → `test_sec_embeddings_commands_have_catalog_schema` catches it
- Mutation: `xbrl_client._get_user_agent` reverts to `os.getenv("EDGAR_USER_AGENT")` → `test_delegates_to_resolve_user_agent` catches it (empty string returned instead of pipeline value)

## Items implemented

### 1. CIK overrides (`config/sec_cik_overrides.yaml`)
- Created `config/sec_cik_overrides.yaml` with XOM → two CIKs
- Added `load_cik_overrides()` function
- Modified `build_cik_map()` to accept and apply overrides (takes precedence over SEC lookup)
- Modified discovery loop to union filings from all CIKs, dedup by accession
- Added `--cik-overrides-path` CLI argument
- 5 tests: load overrides, build_cik_map with overrides, precedence, discovery union, dedup, mutation proof

### 2. Foreign filers (20-F/40-F/6-K)
- Added `SECTION_PATTERNS_20F` for 20-F section extraction (Item 3.D risk, Item 4 business, Item 5 operating review, Item 8 financials)
- Added `get_section_patterns()` to select patterns by form type
- Modified `extract_sections()` to accept `form_type` parameter
- Modified `process_filing()` to pass form_type through
- Expanded form validation to allow 20-F, 40-F, 6-K
- 7 tests: 20-F discovery, 6-K discovery, mixed forms, 20-F section extraction, 10-K backward compat, fallback, form validation

### 3. Runbook updates
- Added CIK overrides section with usage instructions
- Added foreign filers (20-F/6-K) pass section with example command

### 4. Runbook bundle run commands fix
- Added `--catalog ${catalog} --schema ${schema}` to all 5 `sec_embeddings` commands
- Added test parsing runbook to verify all commands include these flags

### 5. xbrl_client._get_user_agent delegation test
- Added `test_delegates_to_resolve_user_agent` asserting `_resolve_user_agent` is called
- Added `test_mutation_old_env_get_fails` proving the old `os.getenv("EDGAR_USER_AGENT")` path returns wrong value