# BUILD-ui-A2 round 3 (DeepSeek CHANGES_REQUESTED, 2 test-only findings)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek/VERDICT-ui-A2-r2.md`. LF endings, never touch
`.agents/dispatch.sh`, frontend commands from WSL only, COMMIT your work.
1. CoachMarks.test.tsx:324-340 focus trap: move REAL focus outside (`outside.focus()` on an element attached to document.body, or
   userEvent.tab / shift+tab past the last/first control) and assert `document.activeElement` returns inside the dialog. Paste FAILED output
   with the trap listener (CoachMarks.tsx:108-120) deleted.
2. App.test.tsx: render `<App />`, click the header "Take a tour" button, assert `role="dialog"` (aria-label "Guided tour") appears; a second
   case with `qp_tour_application_v1` already stored as seen — the click still opens it. Paste FAILED output with the AppShell click handler's
   dispatch (AppShell.tsx:42-44) removed.
Verdict `.agents/mimo/VERDICT-ui-A2-r3.md`.
