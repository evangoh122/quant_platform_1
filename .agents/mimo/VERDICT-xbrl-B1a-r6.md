# VERDICT: xbrl-B1a — MiMo
**Status:** APPROVED
**Round:** 6

## Blocking findings
(none)

## Non-blocking notes
- `_classify_error` already had the correct 429→rate_limited, 403→forbidden, 5xx→server_error mapping; the root cause was solely that `status_code` was dropped from the exhausted-retry `SecClientError` at `sec_rag_ingest.py:888`.
- Fix is 4 lines in `sec_rag_ingest.py`: added `last_status` tracker, set it on 403/429/503 and ≥500 retry paths, passed to final raise. Zero impact on non-retry paths.
- `ingest_sec_companyfacts.py` required zero changes — `manifest.http_status = e.status_code` and `_classify_error(e)` now receive the correct value.
- 3 new mutation tests prove the fix: reverted code produces `http_status=None, error_category='client_error'`; fixed code produces `http_status=403/429/503, error_category=forbidden/rate_limited/server_error`.

## Checks run
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → 58 passed (55 existing + 3 new)
- Revert mutation (`git archive HEAD | tar -x -C /tmp/revert_check`) → `test_retry_exhaustion_403_manifest` FAILED:
  ```
  > assert failed[0].http_status == 403
  AssertionError: assert None == 403
   +  where None = CompanyFactsManifestEntry(..., http_status=None, ..., error_category='client_error', ...).http_status
  ```