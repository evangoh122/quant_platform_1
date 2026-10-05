# BUILD-ui-A1 — IMPLEMENT NOW

You are MiMo. Branch `feat/ui-enhancement` (worktree qp1-ui). Stay on it — do not create/switch branches. Binding: the spec below,
`docs/ui_enhancement/PLAN.md` and `docs/ui_enhancement/OWNER_PLAN.md`. Commit per numbered item, LF endings, never touch
`.agents/dispatch.sh`, never weaken tests, capture the red phase, paste each named mutation's FAILED output into the verdict.
Run frontend commands from WSL if the Windows UNC path blocks npm: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build'`.
Verdict: .agents/mimo/VERDICT-ui-A1.md.

---

# BUILD-ui-A1: design system, states, and application shell

Implement only A1 from `docs/ui_enhancement/PLAN.md`. This is a MiMo-sized
round. Do not redesign individual data screens yet.

## Numbered changes

1. Update `frontend/src/index.css` with the owner-plan tokens: `--canvas`,
   `--surface`, `--surface-raised`, `--border`, `--text-primary`,
   `--text-secondary`, `--text-muted`, `--accent`, `--positive`, `--warning`,
   `--negative`, and `--info`. Use one accent, one radius scale, a 4/8px
   spacing rhythm, tabular numerals for metrics, monospace only for IDs, and
   visible `:focus-visible` rings. Remove the current forced light/dark
   `color-scheme` behavior if it prevents the solid-surface palette.
2. Add `frontend/src/components/states/LoadingSkeleton.tsx`,
   `EmptyPanel.tsx`, `ErrorPanel.tsx`, `StaleDataNotice.tsx`, and
   `SuccessToast.tsx`. They must be semantic, reusable, keyboard-safe, and
   not expose raw internal exceptions or credentials. Preserve the old state
   components until their consumers can be migrated safely.
3. Add `frontend/src/layout/AppShell.tsx`, `Sidebar.tsx`,
   `MobileNavigation.tsx`, `PageHeader.tsx`, and `StatusBanner.tsx`.
   `AppShell` owns the responsive layout and accepts the current screen,
   navigation callback, health response, and children. Desktop navigation is
   collapsible; mobile navigation is a keyboard-accessible drawer that works
   at 360px. Add `data-tour` attributes for navigation, the header tour
   action, and the Lakebase banner. The header action may emit a named tour
   request event for A2, but A1 must not implement tour behavior.
4. Update `frontend/src/App.tsx` to use the shell and group presentation
   labels under Overview, Research, Strategy, Operations, and Evidence while
   preserving the internal IDs and endpoint behavior. Keep the 30-second
   `/api/health` polling and the current Lakebase degradation rule. Reserve
   destinations for Platform Overview and Architecture & Tests without
   changing existing API routes; a temporary route slot is acceptable until
   A3 supplies those screens.
5. Add or update `frontend/src/App.test.tsx` and a focused shell/navigation
   test file. Cover every current destination, active indicator, mobile drawer
   open/close by keyboard, the global Lakebase banner, and the 360px layout
   contract. Tests must use accessible roles and `data-tour` only for tour
   targeting, never styling classes.

## Tests that must fail on the current code

Add tests with these behaviors before considering the round complete; each
must fail against the pre-A1 implementation:

- `renders grouped navigation and a default Platform Overview destination` —
  current App starts on Market Dashboard and has no Overview destination.
- `marks the selected destination with an accessible active state` — current
  buttons have no tested navigation semantics or grouped labels.
- `opens and closes the mobile drawer with keyboard controls` — current fixed
  aside has no mobile drawer.
- `keeps the Lakebase banner visible when the breaker is open` — retain the
  existing behavior while moving it into `StatusBanner`.
- `exposes a visible header Take a tour action and shell tour targets` — no
  header action or `data-tour` targets exist today.
- `renders a skeleton/empty/error/stale state primitive with semantic status`
  — no state primitive directory exists today.

## Named mutations for DeepSeek

DeepSeek must run or inspect mutations for: active navigation state hardcoded
to the first item; mobile drawer that cannot be dismissed with Escape; a
Lakebase dependency with `circuit_breaker_state: 'open'` not showing the
banner; the `data-tour` attribute removed from the navigation target; and a
360px viewport causing horizontal overflow. The tests must catch each
mutation.

## Acceptance

Run:

```sh
cd frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build
```

Use LF line endings, do not touch `.agents/dispatch.sh`, commit the A1
changes, and write a MiMo verdict naming the commit and test results.

