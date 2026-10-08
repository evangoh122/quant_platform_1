# Codex gpt-5.6-sol review round 2 — XBRL B1a (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

Blocking finding:

1. `pipelines/sec_rag_ingest.py:847-890` and `pipelines/ingest_sec_companyfacts.py:504-506` — When bounded retries are exhausted for HTTP 403, 429, or transient 5xx responses, the final `SecClientError` omits `status_code`. Consequently, the manifest records `http_status=None` and classifies the failure as `client_error`, violating the requirement to record the HTTP status for every CIK fetch. Independent reproduction with five 403 responses produced `attempts=5 status_code=None`. The failure test at `tests/bronze/test_sec_companyfacts.py:1018-1056` covers only a non-retried 404 and misses retry exhaustion.

Confirmed fixed:

- HTTP 403 is retried with bounded backoff.
- `seen_payloads` is updated only after a successful Delta write.
- User-Agent structure validation is enforced without leaking its value.
- Successful and permanent-failure manifests include HTTP status.
- Attempt counts are isolated per concurrent fetch and retained for duplicate manifests.
- Concurrency is capped at four workers.
- Bronze and manifest writers use append mode.
- Raw malformed facts remain preserved.
- No contact email was found in logging paths.
- Driver-side flattening remains non-blocking for B1a, consistent with the prior review.

Validation:

- DeepSeek prerequisite: r5 APPROVED.
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` → 55 passed.
- Independent `/tmp` mutations:
  - Remove 403 retry → 1 failed.
  - Remove structured User-Agent validation → 4 failed.
  - Remove successful manifest HTTP status → 1 failed.
  - Mark payload seen before Delta write → 1 failed.
  - Restore shared request-counter attempt calculation → 1 failed.
- Worktree remained unchanged.
===VERDICT END===
