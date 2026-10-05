# CHECK: XBRL B1b — silver facts + point-in-time as-of view (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Spec: .agents/requests/BUILD-xbrl-B1b.md + docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md §2.3, §2.5 items 3–5. Latest commit on feat/xbrl-silver.
MiMo's verdict is a self-report. Claude: tests/silver + tests/bronze → 470 passed.
1. Named mutations, each must fail a test: information_available_ts from filed_date (or ingest time) instead of bronze_sec_filings_v2.accepted_ts; drop
   accession_number from the silver natural key; sort restatements oldest-first in the as-of selection; publish unresolved accessions to PIT/gold.
2. Identical re-ingest → no duplicate silver rows; two accessions for the same concept/unit/period both survive; first/last observed timestamps kept.
3. SQL: `{catalog}`/`{schema}` placeholders only, no user values; MERGE idempotent; the as-of helper binds `as_of` as a parameter (no f-string value).
4. run_silver_gold.py registers the new step without changing others; a test socket guard exists for the new tests.
