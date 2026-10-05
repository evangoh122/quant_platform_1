# VERDICT: ui-A2 — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None.

## Non-blocking notes
- `vi.useFakeTimers()` in jsdom removes `localStorage`; tests use `Object.defineProperty` to mock it directly.
- `scrollIntoView` and `window.matchMedia` not available in jsdom; mocked in `src/test/setup.ts`.
- `.agents/dispatch.sh` file mode changed by Windows/WSL git artifact; restored before commit.

## Checks run
- `npx vitest --run` → 41/41 pass (5 test files)
- `npx tsc --noEmit` → clean (exit 0)
- `npm run build` → success (185.14 kB JS, 21.21 kB CSS)

## Commit
`8dad99b` on `feat/ui-enhancement`

## Red-phase mutations (named)

1. **Changing a versioned key to an unversioned key:**
   Current code uses `qp_tour_application_v1`. Changing to `qp_tour_application` would cause the tour to re-show to users who already completed it, violating the "auto-start once per key" requirement.

2. **Removing the completion write so the tour reopens after completion:**
   `markTourSeen(storageKey)` is called in `closeTour()` (TourHost.tsx:30) and `useTour.close()` (CoachMarks.tsx:266). Removing either write would cause the tour to auto-start on every page load.

3. **Making a missing selector block Next:**
   Current code sets `rect` to `null` when selector is missing (CoachMarks.tsx:41-43), rendering a centered card. Blocking Next would trap the user on a step with no target.

4. **Removing the focus restore:**
   `openerRef.current?.focus()` is called in `handleClose()` (CoachMarks.tsx:76). Removing it would leave focus on the overlay after closing.

5. **Making ArrowLeft wrap to the last step:**
   Current code uses `Math.max(0, i - 1)` (CoachMarks.tsx:81). Changing to `(i - 1 + steps.length) % steps.length` would wrap to the last step.

6. **Removing the reduced-motion guard:**
   `useTour` checks `window.matchMedia('(prefers-reduced-motion: reduce)').matches` (CoachMarks.tsx:253-255) and returns early if true. Removing this would auto-start tours for users who prefer reduced motion.

7. **Measuring only once so the spotlight is stale after scroll:**
   `measure()` is called on `resize` and `scroll` events (CoachMarks.tsx:68-76). Removing the event listeners would leave the spotlight position stale after the user scrolls or resizes.

## Files created/modified

| File | Action |
|------|--------|
| `frontend/src/components/tours/CoachMarks.tsx` | Created |
| `frontend/src/components/tours/tourSteps.ts` | Created |
| `frontend/src/components/tours/TourHost.tsx` | Created |
| `frontend/src/components/tours/CoachMarks.test.tsx` | Created |
| `frontend/src/App.tsx` | Modified (wire TourHost) |
| `frontend/src/screens/MarketDashboard.tsx` | Modified (data-tour) |
| `frontend/src/screens/ResearchAgent.tsx` | Modified (data-tour) |
| `frontend/src/screens/PaperPortfolio.tsx` | Modified (data-tour) |
| `frontend/src/screens/SystemHealth.tsx` | Modified (data-tour) |
| `frontend/src/test/setup.ts` | Modified (scrollIntoView, matchMedia mocks) |