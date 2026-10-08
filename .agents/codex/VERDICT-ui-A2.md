# Codex gpt-5.6-sol review — UI A2 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `frontend/src/components/tours/CoachMarks.tsx:85`: `handleClose()` executes inside the `setIndex` state updater. This triggers a cross-component state update during render and produced React’s warning during the required test run. The application runs under `React.StrictMode`, where updater functions may execute more than once, so closing/marking a tour can also be duplicated. Move the close side effect outside the updater.
- `frontend/src/components/tours/CoachMarks.tsx:151`: spotlight dimensions use the raw target rectangle plus padding without viewport clamping. A target touching or extending beyond a viewport edge produces negative coordinates or an oversized spotlight, contrary to the requirement that it remain visible after resize and scroll.

Validation:

- DeepSeek r3 prerequisite: APPROVED
- Vitest: 56/56 passed, with the React state-update warning above
- TypeScript: passed
- Production build: passed
- No files edited
===VERDICT END===
