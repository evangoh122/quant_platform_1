# Codex gpt-5.6-sol review — XBRL B1a (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

Blocking findings:

1. `pipelines/sec_rag_ingest.py:830-862` — HTTP 403 responses are treated as permanent failures and never retried. Plan §2.1 explicitly requires bounded exponential backoff for 403 responses.

2. `pipelines/ingest_sec_companyfacts.py:451-480` — `(cik, payload_hash)` is added to `seen_payloads` before the Delta write succeeds. Under concurrency, another matching fetch can be marked `skipped_duplicate` even if the first write subsequently fails, violating the requirement to skip only a payload already committed for that CIK/run.

3. `pipelines/sec_rag_ingest.py:156-176` — User-Agent validation only rejects empties and selected placeholders. Values such as `"foo"` pass despite not having the required application/company and contact-email form.

4. `pipelines/ingest_sec_companyfacts.py:95-108` and `pipelines/ingest_sec_companyfacts.py:646-665` — The ingest manifest has no HTTP-status field, although Plan §2.1 requires HTTP status for each CIK fetch.

Non-blocking findings:

- `pipelines/ingest_sec_companyfacts.py:442-446` — `attempt_count` is calculated from a shared client-wide counter. Concurrent requests can therefore contaminate another CIK’s count.
- `pipelines/ingest_sec_companyfacts.py:451-458` — Duplicate manifests retain the default `attempt_count=1` instead of the calculated count.
- `pipelines/ingest_sec_companyfacts.py:114-175` — Driver-side Python performs parsing and flattening. Driver-side bounded HTTP is acceptable for B1a, but Plan §2.1 calls for parsing and normalization as Spark transformations; this should be addressed in the subsequent lane.
- `tests/bronze/test_sec_companyfacts.py:898-971` — The bounded-concurrency test does not prove `max_workers <= 4`.

Validation:

- DeepSeek prerequisite: r2 APPROVED.
- `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q`: 42 passed.
- Independent `/tmp` mutation proofs:
  - Placeholder-UA acceptance: 3 failed.
  - Removed limiter: 1 failed.
  - Append changed to overwrite: 4 failed.
  - Malformed facts dropped: 2 failed.
  - Duplicate-skip logic removed: 1 failed.
- No repository files were edited.
===VERDICT END===
