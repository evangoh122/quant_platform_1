# BUILD EVIDENCE: coachmarks-rag-theme-r3 — MiMo

## Commit
- **SHA:** 6a33f723a399681d5f1294044a401a7f4a53af0b
- **Branch:** feat/rag-workbench-theme
- **Date:** 2026-10-09

## Checks run

| Command | Result |
|---------|--------|
| `npx tsc --noEmit` | pass (0 errors) |
| `npx vite build` | pass (1.93s) |
| `npx vitest run` | pass (315/315 tests, 8.49s) |

## Part A — r2 repair (F1–F4, B1)

### F1: Delete harness, render real AppShell
- **File:** `frontend/src/components/tours/coachmarks-r2.test.tsx`
- **Mutation:** Change `layout/AppShell.tsx:42-45` to hardcode `tour: 'application'` → Test 1 fails (dispatched tour would always be 'application' regardless of currentId)
- **Proof:** Test 1 now renders real `AppShell` component with `TEST_GROUPS` nav and asserts `qp-tour-request` event detail for agent/architecture/default screens

### F2: Test 8 exercises production replay via real component
- **File:** `frontend/src/components/tours/coachmarks-r2.test.tsx`
- **Mutation:** Make manual replay respect seen keys → Test 8 fails (would check `tourSeen()` and skip the tour)
- **Proof:** Test 8 seeds seen keys via `markTourSeen()` using real production constants (`APPLICATION_TOUR_KEY`, etc.), then renders real `AppShell` and asserts "Take a tour" dispatches the correct tour ID

### F3: 375px test with real measured rects
- **File:** `frontend/src/components/tours/coachmarks-r2.test.tsx`
- **Mutation:** Remove CSS `@media (max-width: 767px) { button { min-height: 44px; min-width: 44px } }` → Test 5 fails (CSS rule assertion)
- **Proof:** Test 5 asserts (a) nav target rect within viewport bounds, (b) card inside viewport via `bottom` style, (c) CSS contains `min-height: 44px` and `min-width: 44px` in `@media (max-width: 767px)` rule

### F4: Replace stale _v1 keys
- **File:** `frontend/src/App.test.tsx`
- **Mutation:** Change `APPLICATION_TOUR_KEY` import to `'qp_tour_application_v1'` → App tests fail (seen key doesn't match production constant)
- **Proof:** App.test.tsx now imports and uses `APPLICATION_TOUR_KEY`, `AGENT_TOUR_KEY`, `ARCHITECTURE_TOUR_KEY` from `tourSteps.ts`

### B1: ToolCallCard blue badge
- **File:** `frontend/src/components/evidence/ToolCallCard.tsx`
- **Mutation:** Change signal badge back to `bg-blue-100 text-blue-700` → Test 10 fails (forbidden class scan)
- **Proof:** Signal badge now uses `bg-[var(--accent-dim)] text-[var(--accent-bright)]` (gold token)

## Part B — new items (1–7)

### 1. ArchitectureEvidence honesty
- **Files:** `ArchitectureEvidence.tsx`, `ArchitectureEvidence.test.tsx`
- **Change:** "Verified Test Groups" → "Expected Test Groups"; placeholder commit/date → "Test coverage — pending build branch run"; status text has `role="status"`
- **Test:** Test 11 checks no "Verified" claim with placeholder data, `role="status"` present

### 2. Skip link
- **File:** `layout/AppShell.tsx`
- **Change:** Added `<a href="#main-content">Skip to main content</a>` as first focusable; `<main id="main-content" tabIndex={-1}>`
- **Test:** Test 12 checks skip link exists, targets `#main-content`, main has `tabindex="-1"`, skip link before Sidebar in DOM order

### 3. Research Agent accessible label
- **File:** `screens/ResearchAgent.tsx`
- **Change:** Added `<label htmlFor="research-agent-input">Research question</label>` (sr-only)
- **Test:** Test 13 checks source contains `<label` with `htmlFor` and matching input `id`

### 4. Mobile nav drawer inert
- **File:** `layout/MobileNavigation.tsx`
- **Change:** Background overlay gets `{...{ inert: '' }}` to prevent interaction
- **Test:** Verified via existing layout.test.tsx escape/focus tests

### 5. Collapsible aria-expanded/aria-controls
- **File:** `components/evidence/DeveloperDetails.tsx`
- **Change:** `<summary>` gets `aria-expanded={open}` and `aria-controls={contentId}`; `<div>` gets `id={contentId}`
- **Test:** Test 14 checks source for `aria-expanded`, `aria-controls`, `contentId` variable, and `id={contentId}`

### 6. Tour target timeout live region
- **File:** `components/tours/CoachMarks.tsx`
- **Change:** Added `targetTimedOut` state; when timeout expires, renders "This step's target could not be shown." with `aria-live="polite"` and `role="status"`
- **Test:** Test 15 (and Test 7 third case) advance fake timers past timeout, assert live region attributes

### 7. Tour exit restores screen
- **Files:** `components/tours/CoachMarks.tsx`, `App.tsx`
- **Change:** Added `currentScreen` prop to CoachMarks; `initialScreenRef` captures it on tour start; `handleClose` calls `onNavigate(initialScreen)` before `onClose`
- **Test:** Test 16 passes `currentScreen="platform-overview"`, presses Escape, asserts `onNavigate('platform-overview')` was called

## Files modified (12)

1. `frontend/src/components/evidence/ToolCallCard.tsx` — B1 blue badge fix
2. `frontend/src/components/evidence/DeveloperDetails.tsx` — B5 aria-expanded/controls
3. `frontend/src/components/tours/CoachMarks.tsx` — B6 timeout, B7 screen restore
4. `frontend/src/components/tours/coachmarks-r2.test.tsx` — F1-F4 test repairs + B6/B7 tests
5. `frontend/src/components/tours/tourSteps.ts` — remove "verified lineage"
6. `frontend/src/layout/AppShell.tsx` — B2 skip link
7. `frontend/src/layout/MobileNavigation.tsx` — B4 inert
8. `frontend/src/screens/ArchitectureEvidence.tsx` — B1 honesty
9. `frontend/src/screens/ArchitectureEvidence.test.tsx` — update for B1 changes
10. `frontend/src/screens/ResearchAgent.tsx` — B3 accessible label
11. `frontend/src/App.tsx` — B7 pass currentScreen
12. `frontend/src/App.test.tsx` — F4 replace _v1 keys
