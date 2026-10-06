# Codex gpt-5.6-sol review — PR #42 fixes (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `pipelines/ingest_sec_companyfacts.py:59-160`: Finding 1 is fixed. The blocked-import run completed with **557 passed, 27 skipped**; no SEC Company Facts schema/DDL contracts were skipped.
- `resources/jobs.yml:111-119`: PyYAML is declared for the task and serverless environment. Finding 2 is fixed.
- `pipelines/ingest_sec_companyfacts.py:615-655`: The reservation and failure-release implementation fixes Finding 3, but its required concurrency regression test is missing. Reverting to mark-seen-after-append in a `/tmp` `git archive HEAD` copy still produced **2 passed** for `tests/bronze/test_sec_companyfacts.py:739` and `:881`. Neither test synchronizes duplicate workers at the pre-append boundary, so the reported race can regress undetected.
- `pipelines/ingest_sec_companyfacts.py:846-856`: Finding 4 is fixed. Removing post-ALTER verification caused `tests/bronze/test_sec_companyfacts.py:2415` to fail as required.
- Schema mutation proof: removing `http_status` from `MANIFEST_COLUMNS` without PySpark caused **8 contract failures**, including `tests/bronze/test_sec_companyfacts.py:1939`.
- Required normal suite: **567 passed, 17 skipped**.
- Live write columns and types remain unchanged.
- Worktree was not edited.

Required change: add a deterministic test that forces two identical `(cik, payload_hash)` workers past fetch concurrently, blocks the first Delta append, and proves only one append occurs. The test must fail when reservation is moved back after the append.
===VERDICT END===
