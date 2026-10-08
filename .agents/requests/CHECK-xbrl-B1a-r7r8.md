# CHECK: XBRL B1a rounds 7+8 — fixes for bugs found by Claude's LIVE runs (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Shell rule: if quoting is hard, write to
`/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`. No .ps1/.bat, no PowerShell
wrappers, nothing in C:\temp. Write .agents/deepseek/VERDICT-xbrl-B1a-r7r8.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line.
Specs: .agents/requests/BUILD-xbrl-B1a-r7.md, -r8.md. Commits 3115a96, 2088db2. MiMo verdicts are self-reports.
Claude live (real Spark + SEC): before r7 every CIK failed (CANNOT_DETERMINE_TYPE) and the manifest write failed (DELTA_METADATA_MISMATCH); after r7
XOM 20,909 + NVDA/AAPL 52,416 facts; r8: MSFT 32,671 facts, no FIELD_ALREADY_EXISTS; the 284-test run no longer writes /tmp/sec_cache.
Mutations, each must fail a test: drop the schema arg from any createDataFrame; remove http_status from the manifest DDL/StructType; ALTER issued
unconditionally; a test writing the real cache dir (remove the autouse fixture → does any test now touch /tmp/sec_cache? check with an inotify-free
approach: compare mtime before/after); cache with <1000 entries accepted; /Volumes fallback removed. Re-run all earlier B1a mutations; offline suite.
