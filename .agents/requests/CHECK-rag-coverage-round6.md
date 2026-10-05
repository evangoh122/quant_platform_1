# CHECK: rag-coverage-round6 (checker: DeepSeek)

Read-only for source: do NOT edit code or tests. Mutation proofs go in /tmp copies (cp -r the repo to /tmp/rag-coverage-round6-mut-*).
Write your verdict to .agents/deepseek/VERDICT-rag-coverage-round6.md between ===VERDICT START=== and ===VERDICT END===,
with "Status: APPROVED" or "Status: CHANGES_REQUESTED", numbered findings with file:line evidence, test counts,
and mutation-proof results. MiMo's own .agents/mimo/VERDICT-* is a self-report, not evidence.

Build request: .agents/requests/BUILD-rag-coverage-round6.md
Previous checker verdict (what had to be fixed): .agents/deepseek/VERDICT-rag-coverage-round5.md
Commits to check: 702e617..HEAD
For EVERY item in the build request: verify it is done (file:line), and re-run each requested mutation proof yourself in /tmp —
the named test must FAIL on the mutated copy. Check no test was deleted or weakened: git diff 702e617..HEAD -- tests.
Run: python -m pytest tests/rag tests/bronze -q (COMBINED) and pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python -m pytest tests/rag -q. Key: notebooks/02_ingest_sec_edgar.py must be a real thin wrapper calling pipelines.sec_rag_ingest.main (no UA/requests/BeautifulSoup); CIK mapping log writer has explicit schema (cik nullable) and batches; main() test asserts exact row content; did the COT TestIdempotency cross-suite failure get root-caused/fixed?
