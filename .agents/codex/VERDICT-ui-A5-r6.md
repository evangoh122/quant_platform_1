# Codex gpt-5.6-sol review — UI A5 r6 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

Findings:

1. `frontend/src/screens/MarketDashboard.tsx:53-71,107-123` — Selecting a range whose rows contain no finite close values replaces the entire chart component with `EmptyState`, including the range selector. The user is then trapped and cannot switch back to “All,” even when older valid data exists. Keep the range controls rendered alongside the selected-range empty state.

Validation:

- DeepSeek fallback gate: APPROVED
- Both r5 fixes confirmed
- Vitest: 175/175 passed
- `npx tsc --noEmit`: passed
- Production build: passed
- Reverting the null-close fix caused its focused test to fail
- Reverting reactive recent-symbol state caused its focused test to fail
- Validation and mutations ran in `/tmp` archive copies
- No tracked files edited
===VERDICT END===

