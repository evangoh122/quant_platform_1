# VERDICT: rag-databricks-round6 — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings

None — all three findings from DeepSeek's check verdict are resolved.

## Fixes applied

### 1. Single `_normalize_as_of` normaliser
- **File:** `api/services/hybrid_retriever.py:39-52`
- Added `_normalize_as_of(as_of)`:
  - `None` → `datetime.now(timezone.utc)`
  - naive → `.replace(tzinfo=timezone.utc)` (treated as UTC, documented)
  - aware → `.astimezone(timezone.utc)`
- Called at the top of: `_pit_filter`, `bm25_search`, `vector_search`, `HybridRetriever.retrieve`, and `search_sec_filings` (in `agent/tools_retriever.py`).
- A naive `as_of` no longer raises `TypeError` and no longer falls into the substring fallback.

### 2. Timezone-safe fallback
- **File:** `agent/tools_retriever.py:138-144`
- Replaced `as_of.strftime("%Y-%m-%d %H:%M:%S")` + `F.lit(...).cast("timestamp")` with epoch-seconds comparison: `F.unix_timestamp(F.col("accepted_ts")) <= F.lit(int(as_of.timestamp()))`.
- **Justification:** `unix_timestamp()` returns seconds since epoch in UTC regardless of Spark session timezone, so the comparison is timezone-invariant. The `as_of` value is already normalised to UTC by `_normalize_as_of`.
- **Concrete test:** `as_of = 2025-06-01 00:00 +08:00` (UTC `2025-05-31 16:00Z`) correctly excludes a filing accepted at `2025-05-31 20:00Z` (`TestNormalizeAsOf.test_plus8_midnight_excludes_filing_at_20utc_previous_day`).

### 3. Point-in-time tests through real retrieval path
- **File:** `tests/rag/test_hybrid_retriever.py`
- Added `TestPITIntegrationRetrieval` (4 tests): calls `bm25_search`, `vector_search`, and `retrieve` with a future-dated chunk (2027) and `as_of=2025-06-01`, asserts exclusion.
- Added `TestPITMutationProof` (2 tests): monkeypatches out the PIT filter from `bm25_search` and `vector_search` respectively, proves the future chunk leaks through — confirming the filter is load-bearing.
- Added `TestNormalizeAsOf` (5 tests): covers `None`, naive, aware UTC, aware non-UTC, and the specific +08:00 scenario from the request.
- Added `test_naive_as_of_returns_hybrid_mode`: naive `as_of` through `search_sec_filings` returns `retrieval_mode == "hybrid"` (not substring fallback).

### Bonus: `_load_corpus` tz fix
- **File:** `api/services/hybrid_retriever.py:293-303`
- `str(row["accepted_ts"])` on a non-UTC Spark session could produce a naive session-local string. Now converts `datetime` objects to UTC ISO format before storing.

## Non-blocking notes

- The dead-code `if "+" not in ts_str and ts_str.endswith(":00"): pass` in `_parse_ts` (line 348) is harmless but should be cleaned up in a future round.
- `vector_search` now always applies PIT filter (no `if as_of is not None` guard) since `_normalize_as_of` guarantees a value. This is correct behaviour — consistent with `bm25_search`.

## Checks run

- `python3 -m pytest tests/rag -q` → **260 passed, 19 skipped** (was 248 passed)
- `python3 -m pytest tests/rag/test_hybrid_retriever.py -q` → **55 passed** (was 43)
- Mutation proof (in-test): removing PIT from `bm25_search` → `FUTURE1` leaks through `test_mutation_remove_pit_from_bm25_fails`
- Mutation proof (in-test): removing PIT from `vector_search` → `FUTURE1` leaks through `test_mutation_remove_pit_from_vector_fails`
- Probe: `as_of = datetime(2025,6,1, tzinfo=timezone(timedelta(hours=8)))` through `_pit_filter` → excludes filing at `2025-05-31 20:00Z` ✓
- Probe: naive `as_of = datetime(2025,6,1)` through `search_sec_filings` → `retrieval_mode == "hybrid"` ✓
- LF line endings verified on all three modified files.