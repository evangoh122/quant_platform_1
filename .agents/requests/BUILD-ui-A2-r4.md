# BUILD-ui-A2 round 4 (Codex sol CHANGES_REQUESTED)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/codex/VERDICT-ui-A2.md`. LF endings, never touch
`.agents/dispatch.sh`, frontend commands from WSL only (`wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`). COMMIT per item.
1. CoachMarks.tsx:85 — `handleClose()` runs inside the `setIndex` updater. Make updaters pure: compute the next index from the current
   value outside the updater (or use an effect), and call close/markTourSeen exactly once. Test: under `<React.StrictMode>`, clicking
   Done/Next-on-last-step calls onClose exactly once and markTourSeen writes once; the test run emits no "Cannot update a component while
   rendering a different component" warning (spy on console.error and assert it was not called with that text).
2. CoachMarks.tsx:151 — clamp the spotlight rectangle (after padding) to the viewport: left/top >= 0, right <= innerWidth,
   bottom <= innerHeight; if the target is fully off-screen, scroll it into view (`scrollIntoView({block:'center'})`, respecting reduced motion
   with `behavior:'auto'`) or fall back to the centered card. Tests: a target at x=-20 and one wider than a 360px viewport produce a spotlight
   inside [0, innerWidth]; the tooltip stays inside the viewport.
Mutations (paste FAILED output in `.agents/mimo/VERDICT-ui-A2-r4.md`): move handleClose back into the updater; remove the clamp.
