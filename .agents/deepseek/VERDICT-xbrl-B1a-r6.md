===VERDICT START===
# VERDICT: xbrl-B1a-r6 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 6

The Codex round-2 blocking finding is fixed and mutation-proof. Retry-exhausted
`SecClientError` now carries the last response `status_code`, so the manifest
records `http_status` and a correct `error_category` (forbidden / rate_limited /
server_error) instead of falling through to `client_error`.

## Blocking findings

None.

## Fix verified

- [pipelines/sec_rag_ingest.py:834] `last_status: Optional[int] = None` tracker.
- [pipelines/sec_rag_ingest.py:849] set `last_status = resp.status_code` on the 403/429/503 retry branch.
- [pipelines/sec_rag_ingest.py:871] set `last_status = resp.status_code` on the transient `>= 500` branch.
- [pipelines/sec_rag_ingest.py:893] final exhausted-retry raise now passes `status_code=last_status`.
- [pipelines/ingest_sec_companyfacts.py:504] `manifest.http_status = e.status_code` and
  [pipelines/ingest_sec_companyfacts.py:506] `manifest.error_category = _classify_error(e)`
  now receive the correct value. No code change required here — `_classify_error`
  [pipelines/ingest_sec_companyfacts.py:558-568] already mapped 429→rate_limited,
  403→forbidden, `>=500`→server_error.
- 3 new mutation tests: [tests/bronze/test_sec_companyfacts.py:1058] (403×5),
  [:1099] (429×5), [:1140] (503×5). Each asserts `http_status`, `attempt_count == 5`,
  and `error_category` in the manifest.

## Specified mutations (each failed a test)

1. Drop `status_code` from the exhausted-retry `SecClientError` (faithful revert of
   `80f607a` pipeline state, keeping the new tests) →
   `test_retry_exhaustion_{403,429,503}_manifest` **3 failed** (`http_status=None`,
   `error_category='client_error'`).
2. Map every failure to `"client_error"` (`_classify_error` returns a constant) →
   `test_classify_error_categories` + the 3 exhaustion tests **4 failed**.

## Earlier B1a mutations re-run (all still caught)

3. Remove 403 retry → `test_mutation_403_not_retried` **1 failed**.
4. Neutralize User-Agent validation → `test_mutation_accept_placeholder_ua` **1 failed**.
5. Drop success-path `manifest.http_status` → `test_manifest_http_status_on_success` **1 failed**.
6. Mark payload seen before Delta write → `test_first_write_failure_allows_second_write` **1 failed**.
7. Restore shared request-counter attempt calc → `test_concurrent_attempt_count_per_cik` **1 failed**.

## Non-retried 404 unchanged

- `test_manifest_http_status_on_failure` (non-retried 404) → **PASSED** (http_status 404 preserved).
- `test_classify_error_categories` → **PASSED** (404→`http_404`, `status_code=None`→`client_error` still intact).

## Non-blocking notes

- The fix touches only `_request`'s retry bookkeeping; `tests/rag/test_sec_rag_ingest.py`
  (203 tests) remains green, confirming no regression to the shared `sec_rag_ingest.py`
  used by PR #28.
- `FakeClock`-driven 403/429/503 tests exercise the backoff path without sleeping, so
  the suite stays offline and fast.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → **58 passed**
- `python3 -m pytest tests/rag/test_sec_rag_ingest.py -q` → **203 passed**
- Offline suite total → **261 passed** (58 + 203)
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py::...::test_manifest_http_status_on_failure tests/...::test_classify_error_categories -v` → **2 passed**
- Mutations 1–7 (in `/tmp/qp1-r6-mutate` copies via `git archive HEAD | tar -x`) → each **failed** as tabulated above.
- Worktree unchanged after checks (`git status --short` clean at `23acc5e`).
===VERDICT END===
