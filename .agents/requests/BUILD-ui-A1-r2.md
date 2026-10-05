# BUILD-ui-A1 round 2 — IMPLEMENT NOW (DeepSeek: 3 named mutations survive; tests only + layout CSS if needed)

You are MiMo. Stay on branch `feat/ui-enhancement`. Fix `.agents/deepseek/VERDICT-ui-A1.md` blocking items. Commit, LF endings, never touch
`.agents/dispatch.sh`, paste each mutation's FAILED output in the verdict (run vitest from WSL if UNC blocks).
1. Active navigation: test navigates to a non-first destination (desktop sidebar AND mobile drawer) and asserts `aria-current="page"` moves to it
   and leaves Platform Overview. Mutation: `item.id === 'platform-overview'` in Sidebar.tsx:44 / MobileNavigation.tsx:80 → FAIL.
2. Breaker rule: fixture with Lakebase `ok: true` + `circuit_breaker_state: 'open'` → banner shown; and `ok: true` + `closed` → hidden.
   Mutation: drop `|| d.circuit_breaker_state === 'open'` (AppShell.tsx:47) → FAIL.
3. 360px contract: a test that renders the shell at 360px and asserts the layout contract that jsdom can check — the drawer's width class
   caps at `min(80vw,320px)`, the main content uses `min-w-0`/`max-w-full` (no fixed widths > 360px on shell/sidebar/header containers), and
   tables are wrapped in horizontally scrollable containers. Mutation: give the shell header a fixed `w-[400px]` → FAIL.
Acceptance: `cd frontend && npm ci && npx vitest --run && npx tsc --noEmit && npm run build`. Verdict: .agents/mimo/VERDICT-ui-A1-r2.md.
