# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — PR #42 fixes (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `tests/bronze/test_sec_companyfacts.py:1788,1942`: Bronze and manifest StructType/DDL contract classes are skipped when PySpark is unavailable. CI therefore does not check the important schema contract (33 skipped tests).
- Current CI-style run: 523 passed, 59 skipped.
- Findings 2–4 are covered; their targeted tests pass and fail under `/tmp` mutations:
  - `resources/jobs.yml:113,119`
  - `pipelines/ingest_sec_companyfacts.py:617-658`
  - `pipelines/ingest_sec_companyfacts.py:846-858`

===VERDICT END===
