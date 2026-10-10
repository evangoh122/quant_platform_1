# Build: repair r2 test proofs + P0 honesty and accessibility (r3)

Builder: MiMo. Checker: DeepSeek. Final: Codex, then Claude Opus. Follow AGENTS.md.

## Objective

On top of the validated r2 commit, close the remaining P0 gaps from the Codex
parity review. No backend/API/dependency changes. Do not deploy or start the
Databricks app.

## Required changes

1. `ArchitectureEvidence.tsx`: remove "Verified" wording wherever the SHA/date
   shown is a placeholder. Label as "Test coverage" / "Expected test groups".
   Status text must be conveyed to screen readers. A "verified" claim is only
   allowed if backed by real data in the component props.
2. Add a skip link ("Skip to main content") as the first focusable element in
   the shell, targeting a stable `<main id="main-content" tabindex="-1">`.
3. Give the Research Agent input an explicit accessible label
   (`<label>` or `aria-label`), not placeholder-only.
4. Mobile navigation drawer: modal behavior — Escape closes, focus contained
   while open, focus restored to the opener on close, background `inert`.
5. Every collapsible evidence disclosure gets `aria-expanded` and
   `aria-controls` that reference a real id.
6. Tours: when the target cannot be shown after the bounded timeout, render an
   explicit "This step's target could not be shown" state (announced via a
   polite live region), not a plain centered card. Screen changes made by a
   tour are announced.
7. Tour exit behavior: on skip or finish, restore the screen the user started
   from. Test it.

## Tests (must fail on the r2 commit, pass after)

One behavior test per numbered item (render real components, assert DOM/ARIA
and focus; no copied production logic). Name the production mutation each test
catches in your evidence file, and actually run each mutation to show the test
fails.

## Acceptance

`npm run lint`, `npm run build`, `npm test` in `frontend/` all pass. Commit all
changes. End with exactly one line:
`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/rag-workbench-theme | evidence: <path>`

## Part A — repair r2 (binding; from `.agents/deepseek/VERDICT-coachmarks-rag-theme-r2.md`)

Base: r2 commit `a3c1236019a7e6a70b9050180ec34fa9d0f41273`. DeepSeek found these
test defects; fix them FIRST and re-prove with mutations:

- **F1** `frontend/src/components/tours/coachmarks-r2.test.tsx:168-178` re-implements
  AppShell's route ternary in a harness. Delete the harness. Render the real
  `AppShell` (or real `App`) and assert the real `qp-tour-request` event detail
  for agent / architecture / default screens. Mutation: change
  `layout/AppShell.tsx:42-45` to hardcode `tour: 'application'` -> tests must fail.
- **F2** Test 8 ("seen key = 1") must exercise production replay behaviour via the
  real component: seed the seen keys through the real storage key constants and
  assert manual "Take a tour" still opens the route-correct tour. Mutation:
  make manual replay respect seen keys -> test must fail.
- **F3** The 375 px test must assert (a) the nav target is within the viewport
  using real measured rects (stub `getBoundingClientRect`/`innerWidth` as needed),
  (b) the card is inside the viewport, (c) every tour control has computed
  min width/height >= 44px. jsdom does not apply `@media`; assert via a shared
  constant/class that the production code and CSS both use, or read the rule from
  `index.css`. No `expect(btn).toBeTruthy()` placeholders.
- **F4** `frontend/src/App.test.tsx:153-155`: replace stale `_v1` keys with the
  current versioned keys imported from `tourSteps.ts`, and assert the dispatched
  tour id for each screen.
- **B1 (harness, already fixed by coordinator)**: acceptance runs under non-interactive
  bash; put `export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"` at the top of
  any `.agents/run-*.sh` you create, and assert `command -v node npm npx` do not resolve
  under `/mnt/`.
- Also resolve the remaining blue "running" badge at
  `frontend/src/components/evidence/ToolCallCard.tsx:36`: use the shared semantic
  info/gold token instead of `bg-blue-*`, and add a test that no non-test tsx
  contains `bg-white|bg-slate-|text-slate-|bg-blue-|text-blue-|border-slate-`.

## Part B — the items above (1-7)
