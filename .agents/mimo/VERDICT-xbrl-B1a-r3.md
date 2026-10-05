# VERDICT: xbrl-B1a — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
(none — all 4 blocking items resolved)

## Fixes applied

### 1. HTTP 403 retry with bounded exponential backoff
- `pipelines/sec_rag_ingest.py:830` — Added 403 to retry condition `(403, 429, 503)` with same bounded exponential backoff as 429: honours Retry-After (capped), else `min(2^attempt, 60)` backoff.
- Mutation test: `test_mutation_403_not_retried` in `tests/bronze/test_sec_companyfacts.py` — FAIL if 403 not retried.

### 2. seen_payloads.add AFTER Delta write
- `pipelines/ingest_sec_companyfacts.py:460-488` — Moved `seen_payloads.add((cik, payload_hash))` after successful Delta write, guarded by lock.
- Mutation test: `test_first_write_failure_allows_second_write` — first Delta write raises → identical second payload is written (not skipped).

### 3. UA validation: `<name> <email>` format
- `pipelines/sec_rag_ingest.py:156-190` — Added regex `^[^\s]+(\s+[^\s]+)*\s+[^\s]+@[^\s]+\.[^\s]+$` requiring non-empty name token + email with domain dot.
- Rejects: `"foo"`, `"foo bar"`, `"a@b"`, `"user@localhost"`.
- Accepts: `"MyApp/2.0 contact@company.com"`, `"Acme Corp contact@acme.com"`.
- Tests: 6 new accept/reject cases in `TestUserAgentValidation`.

### 4. http_status in manifest
- `pipelines/ingest_sec_companyfacts.py` — Added `http_status: Optional[int]` to `CompanyFactsManifestEntry`, `MANIFEST_COLUMNS`, DDL (`ensure_table`), `write_manifest`, and fetch logic.
- `fetch_company_facts` now returns `(payload, raw_bytes, payload_hash, http_status)`.
- Tests: `test_manifest_http_status_on_success` (200), `test_manifest_http_status_on_failure` (404), updated `test_manifest_fields_complete`.

### Non-blocking items addressed
- `attempt_count` is computed per-CIK from `client.request_count - req_before` (already thread-local snapshot).
- Concurrency test `test_bounded_concurrency_max_workers` passes (6 tickers, 4 max_workers).

## Checks run
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **52 passed**
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → **203 passed**
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py tests/bronze/test_sec_companyfacts.py -q` → **255 passed**
- `python3 -m py_compile pipelines/sec_rag_ingest.py` → OK
- `python3 -m py_compile pipelines/ingest_sec_companyfacts.py` → OK