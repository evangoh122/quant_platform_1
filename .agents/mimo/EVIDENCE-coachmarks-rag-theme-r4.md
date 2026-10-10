# BUILD EVIDENCE: coachmarks-rag-theme-r4 — MiMo

## Commit
- **SHA:** `bd73396a07fa97b60584efe8ef2d8f48086d0a19`
- **Branch:** `feat/rag-workbench-theme`
- **Message:** `fix(tours): reset only on run start; restore starting screen`
- **Base:** r3 commit `6a33f723a399681d5f1294044a401a7f4a53af0b` (parent of the r3 routing commit `66fc53f`)
- **Scope:** `frontend/src/components/tours/CoachMarks.tsx` + `frontend/src/components/tours/coachmarks-r2.test.tsx` only. No backend/API/dependency change. No deploy.

## Acceptance checks (via `.agents/run-coachmarks-rag-theme-r4-check.sh`, wsl Ubuntu, node v26.5.0)

| Command | Result |
|---------|--------|
| `npx tsc --noEmit` | pass (0 errors) |
| `npx vitest run` | pass (320/320 tests, 16 files) |
| `npm run build` | pass (tsc && vite build, 68 modules) |
| legacy light-style grep (non-test tsx) | `none` |
| node/npm/npx boundary (`/mnt/*` rejects) | pass (all under `~/.nvm/versions/node/`) |
| `git rev-parse HEAD` == committed SHA | pass |
| `git status --porcelain --untracked-files=no` | clean |
| `git merge-base --is-ancestor origin/main HEAD` | pass |
| `git diff --check origin/main...HEAD` | clean |
| sentinel | `r4 check script finished` (old `r2 check script finished` sentinel removed; r3 script renamed to `.agents/run-coachmarks-rag-theme-r4-check.sh`) |

## B1 fix (blocking bug from `.agents/deepseek/VERDICT-coachmarks-rag-theme-r3.md`)

`frontend/src/components/tours/CoachMarks.tsx`:

- Before: the reset effect was keyed on `[run, currentScreen]`, so every `navigateTo` step (which changes `currentScreen` through `onNavigate` → `App` `setScreen`) re-ran `setIndex(0)` and overwrote `initialScreenRef` with the *destination* screen. Steps after a `navigateTo` step were unreachable (tour looped to step 1) and close restored the wrong screen.
- After: `currentScreenRef` mirrors the latest `currentScreen` during render (same pattern as `TourHost.tsx`'s `screenRef`), and the reset effect is keyed on `[run]` only, reading `currentScreenRef.current` when `run` turns true. `currentScreen` is **not** a dependency of the reset.

```diff
-  }, [run, currentScreen]);
+  }, [run]);
...
-      initialScreenRef.current = currentScreen;
+      initialScreenRef.current = currentScreenRef.current;
```

## Required tests (all render real components; no vacuous harness)

All in `frontend/src/components/tours/coachmarks-r2.test.tsx` unless noted.

### 1. Stateful cross-screen tour (real `App`, real `useState` screen state)
`Test 16: Stateful tour advances past every navigateTo step and restores the starting screen` (4 cases):

- `application tour reaches the last step past every navigateTo step ... Done restores the starting screen`: renders the real `App` (fetch mocked, all three seen keys marked), starts on **`signals`** (non-default screen), opens the application tour via the real header button. Walks all 5 steps. For **every** `navigateTo` step (3/5 market, 4/5 agent, 5/5 health) asserts: step counter is `Step N of 5` after settling (never `Step 1 of 5`), the step's real screen target (`[data-tour="market-research"|"agent"|"analytics-evidence"]`) is in the DOM with non-zero `getBoundingClientRect()`, the waiting state is cleared (CoachMarks found the target), and the CoachMarks spotlight is measured (inline `box-shadow` rect with `width > 0`). Collects every counter and asserts `['Step 1 of 5','Step 2 of 5','Step 3 of 5','Step 4 of 5','Step 5 of 5']` — strictly monotonic. Clicking **Done** calls `onNavigate('signals')`: the app ends on `signals` (`aria-current="page"` on the Signal Explorer nav button).
- `Escape after a navigateTo step restores the screen the user started on`: starts on `signals`, navigates to `market` mid-tour, Escape → ends on `signals`.
- `Skip tour after a navigateTo step restores the screen the user started on`: same with the Skip control.
- `close calls onNavigate with the screen the user started on (stateful harness)`: harness whose `onNavigate` really updates `currentScreen` via `useState` (mirrors `App`'s stable-callback wiring) and records calls. After the `navigateTo` step: `navCalls == ['market']`, screen state shows `market`, counter is `Step 2 of 2` (not reset). Escape → `navCalls == ['market','signals']` (the restore call) and screen state shows `signals`.

This proves (a) advance past every `navigateTo` step with each target visible/non-zero, (b) monotonic step counter, (c) closing/finishing/skipping calls `onNavigate(<starting screen>)` and the user ends there, including a non-default start (`signals`).

### 2. Static-prop Test 16 replaced
The vacuous `Test 16` (static `currentScreen="platform-overview"`, mock `onNavigate` that never updated the prop) is **deleted** and replaced by the stateful suite above.

### 3. Source-scan tests converted to rendered DOM/ARIA
- `Test 11` → renders `<ArchitectureEvidence />`: asserts `role="status"` element in the DOM, `Expected Test Groups` heading, `Test coverage` text, and **no** `Verified` claim nodes.
- `Test 12` first case → renders `<AppShell />`: skip link is the **first focusable element in DOM order** and targets `#main-content`; `main#main-content` has `tabindex="-1"` (second case retained as rendered assertion).
- `Test 13` → renders `<ResearchAgent />`: `getByRole('textbox', { name: /research question/i })` finds the input with `id="research-agent-input"` (real label association).
- `Test 14` → renders `<DeveloperDetails />`: `<summary>` has `aria-expanded="false"` and `aria-controls="developer-details-content"`, the referenced id exists in the DOM, and `aria-expanded` tracks the real toggle state. No source scan remains.

### 4. Mobile drawer `inert`
`Test 17: Mobile drawer background is inert while open` renders the real `AppShell` → `MobileNavigation`: closed → no `[inert]` node; open (real toggle button) → background overlay carries `inert` + `aria-hidden="true"` while the drawer `role="dialog"` does not; Escape close → `inert` gone.

### 5. Evidence accuracy + check script
- Replay-ignores-seen-keys proof corrected: the production proof is `App.test.tsx` "opens the tour dialog when Take a tour is clicked even if already seen". The misleading `Test 8` claim is gone; `Test 8` is rewritten to assert something real — renders the full `App` + `TourHost` with every seen key = 1 and proves manual "Take a tour" still opens the route-correct tour (agent screen → `Research Agent tour`, default screen → `Welcome to QP1`).
- Sentinel `r2 check script finished` removed; `.agents/run-coachmarks-rag-theme-r3-check.sh` renamed to `.agents/run-coachmarks-rag-theme-r4-check.sh` with the new commit SHA pattern, `export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"` and the `/mnt/` boundary assertion retained.

### 6. Commit message
`fix(tours): reset only on run start; restore starting screen` with a descriptive body.

## Mutation testing (isolated `git archive` copies under `/tmp/r4mut`, node_modules symlinked; `git archive` only, never `git` inside a `cp -r` copy)

Each row: mutation applied to a fresh archive of `bd73396a07fa97b60584efe8ef2d8f48086d0a19`, target test re-run, expected FAIL observed.

| # | Mutation | Target test | Result |
|---|----------|-------------|--------|
| M1 | put `currentScreen` back into the reset effect deps (`CoachMarks.tsx`) | `Test 16` (4 cases) | FAIL — `findByText('Step 3 of 5')` times out; harness shows `Step 1 of 2` (the exact loop-to-step-1 defect) |
| M2 | overwrite `initialScreenRef` on every render | `Test 16` (4 cases) | FAIL — harness restore call becomes `['market','market']` (wrong screen restored); real-App cases end on `market`, not `signals` |
| M3 | remove `inert` from the drawer (`MobileNavigation.tsx`) | `Test 17` | FAIL — `expected null not to be null` at the `[inert]` assertion |
| M4 | remove `aria-controls` from the evidence disclosure (`DeveloperDetails.tsx`) | `Test 14` | FAIL — `aria-controls` attribute is `null` |
| r3-M1 | hardcode `tour:'application'` in `AppShell.tsx` | `Test 1: Header` | FAIL — agent + architecture cases expect `['agent']/['architecture']`, receive `['application']` |
| r3-M2 | `TourHost` `qp-tour-request` handler respects seen keys | `App.test.tsx` "even if already seen" **and** `Test 8` | FAIL — tour dialog never opens (2/2 Test 8 cases + App case fail) |
| r3-M3 | remove the 44px `@media` rule (`index.css`) | `Test 5` | FAIL — CSS `min-height/min-width: 44px` regex no longer matches |
| r3-M4 | stale `_v1` seen keys in `App.test.tsx` | `App.test.tsx` "does not auto-start agent tour" | FAIL — real keys unseen, application tour auto-starts, dialog found |
| r3-M5 | restore `bg-blue-100 text-blue-700` badge (`ToolCallCard.tsx`) | `Test 10` | FAIL — forbidden-class scan finds `bg-blue-100` |
| r3-M6 | remove `aria-expanded` (`DeveloperDetails.tsx`) | `Test 14` (rendered) | FAIL — both rendered cases see attribute `null` |
| r3-M7 | remove the skip link (`AppShell.tsx`) | `Test 12` | FAIL — both rendered cases cannot find "Skip to main content" |
| r3-M8 | drop Escape handling (`MobileNavigation.tsx`) | `layout.test.tsx` "restores focus to trigger after closing the drawer" | FAIL — drawer never closes |
| r3-M9 | remove `onNavigate(initialScreenRef)` in `handleClose` | `Test 16` (4 cases) | FAIL — harness `navCalls == ['market']` (no restore call); real-App cases end off-start |

**Failing-before on the r3 base:** `git archive 6a33f723a399681d5f1294044a401a7f4a53af0b` with the new `coachmarks-r2.test.tsx` overlaid → `Test 16` fails 4/4 (`Step 1 of 2` reset; missing restore). The new tests detect the original B1 defect on the unpatched base.

## Files modified (2)
1. `frontend/src/components/tours/CoachMarks.tsx` — B1 reset fix (`[run]`-keyed effect, `currentScreenRef` for the restore target)
2. `frontend/src/components/tours/coachmarks-r2.test.tsx` — Test 16 stateful replacement, Test 8 real replay rewrite, Test 11/12/13/14 rendered conversions, Test 17 inert

## Non-blocking notes
- `CoachMarks`' step `useLayoutEffect` re-fires `onNavigate(step.navigateTo)` if a caller passes an unstable `onNavigate`/`steps` identity. The real `App` is safe (`useTourHost.handleTourNavigate` is `useCallback([])`, `steps` is set once per tour); the stateful harness mirrors that wiring. Worth a defensive guard in a future round.
- jsdom does not toggle `<details>` on `summary` click; `Test 14`'s state-tracking case dispatches the real `toggle` event on the `<details>` element, which exercises the component's `onToggle` handler.

BUILD DONE | status: SUCCESS | sha: bd73396a07fa97b60584efe8ef2d8f48086d0a19 | branch: feat/rag-workbench-theme | evidence: .agents/mimo/EVIDENCE-coachmarks-rag-theme-r4.md
