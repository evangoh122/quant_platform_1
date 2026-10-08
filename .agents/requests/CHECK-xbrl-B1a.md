# CHECK: XBRL B1a — SEC Company Facts client + append-only bronze (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies; never run git inside a copy. Write
.agents/deepseek/VERDICT-xbrl-B1a.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Spec: .agents/requests/BUILD-xbrl-B1a.md + docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md §2.1, §2.2, §2.5. Commits 3983aed..762ca56.
MiMo's verdict is a self-report. Claude: tests/bronze/test_sec_companyfacts.py → 34 passed; live `--dry-run --tickers NVDA,XOM` → mapped=2,
ticker-CIK pairs=3 (stops before fetching).
1. Run the four named mutations (accept a placeholder UA; remove the rate limiter; overwrite instead of append; drop malformed facts) on the
   SHIPPED code — each must fail a test. "Mutation tests" that only re-implement logic inline are a blocking finding.
2. Bronze columns match Plan B §2.2 exactly; `ingested_at` is collection time only; Delta write mode is append; table created if absent.
3. Rate limit: process-wide ≤10 req/s even with concurrency (shared limiter, not per-thread); Retry-After honoured; bounded retries;
   timeouts; no response bodies or the contact email logged (grep log calls).
4. Parsing/normalisation are Spark transformations (driver only fetches) per Plan B §2.1 — or, if MiMo flattened in Python, is that acceptable
   for payload sizes (NVDA companyfacts ≈ several MB)? Report; judge severity.
5. resources/jobs.yml job: params, secret scope/key, ordering note; bundle-sync tests updated, not weakened.
6. `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` and report.
