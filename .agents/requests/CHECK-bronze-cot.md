# CHECK-REQUEST (DeepSeek = checker): bronze-cot round 2

You are the **checker**, not the builder. Do not modify production code or tests. Read and run.
Branch `slice/bronze-cot`, worktree `/home/jianj/code/qp1-b-cot`.
Round-2 and round-3 requests: `.agents/requests/BUILD-bronze-cot-round2.md`. Codex's round-1 findings:
`.agents/codex/VERDICT-bronze-cot.md`. Diff since your last check: `git diff 0e3c9f6..HEAD`. Your previous verdict: `.agents/deepseek/VERDICT-bronze-cot-check.md` (off-by-one test was tautological).

Claude already verified (round 3): the date filter is now `filter_report_window()` (notebooks/refresh_bronze_cot.py:343) and restoring the round-1 bug (`parsed > start_ts`) in a scratch copy makes 6 tests fail while 41 pass on HEAD. Earlier: no `overwrite` write path remains; 36 tests pass; tests reference the
production functions 28 times; no CRLF; a live `--dry-run` reports 0 new rows for both datasets
(tables are current to CFTC's latest published report, 2026-09-22).

Check independently:
1. Is the write path strictly append-only, including table creation when a table is missing?
2. Does verification run **before** status is set OK — row delta == appended count, all keys present,
   zero duplicate keys — and does a failed check give a nonzero exit?
3. Is the off-by-one fixed, with a test using a report dated exactly max+1 day?
4. Would each test **fail if the production function it covers were broken**? Pick two tests and
   reason concretely (or mutate a copy of the function in /tmp and run the test against it — never
   edit files in the worktree).
5. Anything that could duplicate rows on a re-run.

Run `python3 -m pytest tests/bronze/test_refresh_bronze_cot.py -q`. Output a verdict
**APPROVED** or **CHANGES_REQUESTED** with file:line evidence, printed between lines
`===VERDICT START===` and `===VERDICT END===`. Write it to `.agents/deepseek/VERDICT-bronze-cot-check.md`
and commit only that file.
