# VERDICT: xbrl-B1a round 8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
None

## Non-blocking notes
- Bug 1 fix: `ensure_table` now checks if `http_status` column exists before running ALTER TABLE, preventing `[FIELD_ALREADY_EXISTS]` error logging
- Bug 2a fix: Added `tests/bronze/conftest.py` with autouse fixture that monkeypatches `tempfile.gettempdir()` to return `tmp_path`, preventing test pollution of real fallback cache path
- Bug 2b fix: Modified `_try_load_cache` to treat caches with fewer than 1,000 entries as invalid when `is_fallback=True`
- Updated `load_company_tickers` to accept `is_fallback` parameter and pass it to `_try_load_cache`
- Updated callers in both `ingest_sec_companyfacts.py` and `sec_rag_ingest.py` to pass `is_fallback=True` when using fallback cache path
- Added comprehensive tests for both fixes
- All existing tests pass (81 bronze tests, 203 rag tests)

## Checks run
- `python -m pytest tests/bronze/test_sec_companyfacts.py -x --timeout=60 -q` → 81 passed
- `python -m pytest tests/rag/test_sec_rag_ingest.py -x --timeout=60 -q` → 203 passed
- `python -m pytest tests/bronze/test_sec_companyfacts.py::TestEnsureTableIdempotent -xvs` → 2 passed
- `python -m pytest tests/bronze/test_sec_companyfacts.py::TestCacheMinEntries -xvs` → 4 passed
- `python -m pytest tests/rag/test_sec_rag_ingest.py::TestCikCache -xvs` → 2 passed