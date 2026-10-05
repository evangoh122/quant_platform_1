# CHECK: CDC analytics fast-track (checker: DeepSeek) — FAST (submission in ~2 h; keep to ~25 min)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-analytics-cdc.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", with file:line evidence.
Request: .agents/requests/BUILD-analytics-cdc-fast.md (+ docs/rubric/BUILD-analytics-cdc.md). Commits 8888b79..e2b5c9e. Claude: tests 359 passed.
Focus ONLY on blocking correctness/safety (ships today): (1) migration 004 is valid Postgres, idempotent on re-apply, triggers write the outbox in
the SAME transaction, payloads use explicit field lists (no note text / summaries / credentials), SECURITY DEFINER functions have a fixed
search_path and revoked public execute; (2) the runner is watermarked and idempotent (replay does not duplicate; MERGE not append);
(3) analytics.py returns real aggregates or an explicit no_data_yet state — no placeholder envelopes; queries use named params via the adapter;
(4) jobs.yml entry is valid. Re-run mutations WATERMARK-SKIP, APPEND-DUPLICATE, LEAK-NOTE-TEXT, PLACEHOLDER-ROUTE → each must FAIL a test.
Run: python3 -m pytest -q tests/rubric tests/api --timeout 60.
