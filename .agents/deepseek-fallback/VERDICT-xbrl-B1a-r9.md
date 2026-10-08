# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — xbrl-B1a-r9 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `pipelines/ingest_sec_companyfacts.py:807`: legacy ALTER path hard-codes `http_status INT` instead of deriving the missing column/type from the manifest `StructType`.
- `pipelines/ingest_sec_companyfacts.py:176-219`: unused hand-written `BRONZE_FACT_COLUMNS` and `MANIFEST_COLUMNS` remain, contrary to the single-source-of-truth requirement.

Validation:
- 288 tests passed offline excluding the environment-dependent fallback test.
- Full suites: 289 passed, 1 failed because `test_fallback_when_volumes_not_writable` attempted DNS/network access to SEC.
- StructType-drop mutations failed as required in isolated `/tmp` archive copies.
===VERDICT END===
