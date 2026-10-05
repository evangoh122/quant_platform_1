# BUILD-ui-A2 round 2 — IMPLEMENT NOW (DeepSeek CHANGES_REQUESTED on A2)

You are MiMo. Branch `feat/ui-enhancement` (stay on it; no new branches). Fix every blocking finding in
`.agents/deepseek/VERDICT-ui-A2.md` (read it first). Commit per item, LF endings, never touch `.agents/dispatch.sh`.
Frontend commands from WSL only: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`.
Never `npm ci` from Windows. COMMIT your work (round 1 of another lane was left uncommitted).

1. Delete the dead `useTour` hook (CoachMarks.tsx:247+) and its tests, OR make the app use it — one auto-start path only.
   Move the auto-start / reduced-motion / mark-seen tests onto the path the app actually runs (`useTourHost` / TourHost.tsx).
2. Versioned keys: test asserts localStorage key `qp_tour_application_v1` (and the agent/architecture keys) is written on Done and on Skip,
   and that a stored `_v1` key prevents auto-start.
3. Focus restore: test that after Escape (and after Done) `document.activeElement` is the opener element.
4. Spotlight reposition: test that changes the target's getBoundingClientRect, fires `resize` and `scroll`, and asserts the spotlight
   style/position updates.
5. Focus trap: test that Tab / Shift+Tab from the last/first control stays inside the dialog.
6. Header replay: test clicks "Take a tour" in the rendered app and asserts the tour dialog opens (via the real `qp-tour-request` path),
   including after the tour was already marked seen.
7. Missing-selector test: make it non-vacuous — distinct step titles (not "Next"), assert the SECOND step's title is shown after clicking
   the Next button.

Mutations to run and paste FAILED output for in `.agents/mimo/VERDICT-ui-A2-r2.md`: all seven named mutations in BUILD-ui-A2.md applied
to the production path, plus: remove `markTourSeen` in TourHost.tsx; remove the reduced-motion guard in TourHost.tsx.
Every one must FAIL at least one test.
