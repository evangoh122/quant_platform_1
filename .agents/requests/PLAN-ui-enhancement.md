# PLAN: capstone UI enhancement (planner + later final reviewer: Codex gpt-5.6-sol)

Owner request: "Get codex to build with mimo and deepseek" the plan in `docs/ui_enhancement/OWNER_PLAN.md` (binding).
Workflow (fixed): MiMo builds each slice → DeepSeek checks → Codex sol final review → Claude live validation (deploys to the Databricks
App and screenshots) → PR + CodeRabbit. You PLAN now; do not implement. Write under `docs/ui_enhancement/` (you may not be able to write `.agents/`).
Read: the current frontend (`frontend/src/**`, `api/routes/**` for the contracts it uses — agent chat, analytics, health, market,
signals, portfolio, watchlists, orders), and the Rag_workbench reference UI at /home/jianj/code/Rag_workbench/frontend/src
(CoachMarks.tsx, tourSteps.ts, AuditTrail.tsx, SystemDashboard.tsx, PipelineFlow.tsx — concepts only).
Deliverables: `docs/ui_enhancement/PLAN.md` (slice order, file ownership so slices never edit the same files concurrently, the exact
API response shapes each new component consumes — verify against the code, not the owner plan's assumptions) and one
`BUILD-ui-<slice>.md` per MiMo-sized round (≈45–60 min each): numbered changes with file paths, Vitest + Testing Library tests that
must fail on the current code, named mutations for DeepSeek (e.g. tour reopens after completion; raw JSON expanded by default; empty
analytics rendered as 0; missing tour target traps the user), and acceptance commands (`cd frontend && npm ci && npm test -- --run &&
npx tsc --noEmit && npm run build`). Slice A first: A1 design tokens + states + AppShell/navigation; A2 coach marks + tours;
A3 Platform Overview + Architecture & Tests; A4 Research Agent redesign + evidence cards; A5 SymbolPicker + market chart.
Print `MIMO_BUILD_NEEDED: docs/ui_enhancement/BUILD-ui-A1.md` at the end.
