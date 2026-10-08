# CHECK: UI slice A2 — coach marks and tours (checker: DeepSeek)

Read-only on the worktree. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` + symlink frontend/node_modules
(run vitest from WSL: `wsl -d Ubuntu -- bash -lc 'cd <copy>/frontend && npx vitest --run'`). Never run git inside a copy.
Write .agents/deepseek/VERDICT-ui-A2.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", every finding with file:line.

Spec: .agents/requests/BUILD-ui-A2.md (binding) + docs/ui_enhancement/OWNER_PLAN.md Phase 2. Commit under check: 8dad99b.
MiMo's own verdict (.agents/mimo/VERDICT-ui-A2.md) is the builder's self-report, not evidence.
Claude (WSL): vitest 41 passed; tsc clean.

Do:
1. Run every named mutation in BUILD-ui-A2.md ("Named mutations for DeepSeek") yourself and paste the FAILED output. Any mutation
   that survives (all tests still pass) is a blocking finding.
2. Confirm each "Tests that must fail on the current code" test exists and is non-vacuous (asserts behaviour, not just render).
3. Check constraints: no disclaimer dependency, no RAG copy, no `glass-*` classes, no old workbench service imports; `data-tour`
   attributes (not classes); exact keys qp_tour_application_v1 / qp_tour_agent_v1 / qp_tour_architecture_v1; dialog semantics
   (role=dialog, aria-modal, labelled); overlay blocks page interaction; tooltip stays inside a 360px viewport.
4. Confirm A1 tests still pass and A1 behaviour is not regressed.
