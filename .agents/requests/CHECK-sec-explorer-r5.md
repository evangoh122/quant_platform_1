# CHECK: SEC Filing Explorer round 5 — CodeRabbit #41 findings incl. security (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD` (+ symlink frontend/node_modules). Print the verdict to stdout between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Findings: .agents/coderabbit-pr41.md. Fixes 6ab07f9 (identity dependency + demo gate on /api/sec/coverage), 3a77095 (frontend). Claude: frontend 24 passed,
tests/api 327 passed; removing `Depends(get_current_user)` from the route → a test fails.
1. /api/sec/coverage follows exactly the same identity and demo pattern as api/routes/market.py (read api/deps.py): untrusted/no identity → rejected like market;
   public demo → read_delta never runs the live callback. Mutations: drop the dependency; call the reader directly instead of via read_delta → each fails a test.
2. Each frontend finding (SecFilingExplorer.tsx:150, :226, :241 + nitpick) fixed with a test that fails on the previous code (clear button invalidates an in-flight
   request, etc.). Re-run all earlier SEC explorer mutations.
