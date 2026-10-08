# BUILD-ui-A5 — IMPLEMENT NOW (A1–A4 approved by the checker + Codex)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Binding spec: `docs/ui_enhancement/BUILD-ui-A5.md` (read all of it) + PLAN.md + OWNER_PLAN.md. LF endings, never touch
`.agents/dispatch.sh`, NEVER run npm ci/install, commit per numbered item, red phase + paste each named mutation's FAILED output (mutate in a `git archive HEAD | tar -x -C /tmp/<dir>` copy
with frontend/node_modules symlinked). Tests may only render production components with mocks that match the REAL backend contracts (api/schemas.py, api/routes/*.py) — never invent fields.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard, use
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`. No PowerShell, nothing in C:\temp. Stage only files you change. Verdict `.agents/mimo/VERDICT-ui-A5.md`.

## 0. First: a regression from merging main (do this before A5 items)
`origin/main` was just merged into this branch (it brings PR #41: frontend/src/screens/SecFilingExplorer.tsx with an equity selector fed by GET /api/sec/coverage, honest
no-coverage/unavailable states, stale-request guard). After the merge ONE test fails:
`src/layout/layout.test.tsx > Navigation destination enumeration > navigates to each destination on click and preserves aria-current` — "Unable to find an accessible element with the role
"button" and name "AI Research Agent"". Find the cause (likely the new SEC screen's coverage fetch is unmocked or it changes focus/landmarks) and fix it properly (mock /api/sec/coverage in
the shared test setup with the real response shape {data, count, status}; do not weaken the navigation test). All 144 tests must pass.

## A5 context
- The SEC Research screen now has its own coverage-backed equity selector (228 equities). The shared SymbolPicker (spec items 1–2, 4) must reuse it rather than fight it: for SEC Research,
  the picker's options/coverage indicator come from GET /api/sec/coverage; for market/options they come from frontend/src/data/symbols.json as the spec says. Keep #41's honest states and
  stale-request guard.
