# VERDICT: ui-A4-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
- None.

## Non-blocking notes
- `deriveBadge` now filters error rows from source count for `search_sec_filings`, matching `deriveSourceCount`.
- `deriveBadge` shows "Save not confirmed" instead of "Note saved" when `save_research_note` succeeds but `note_id` is absent.
- Confidence/score rejection test scopes visible content by excluding DeveloperDetails raw JSON, preventing false positives from debug output.

## Checks run
- `npx vitest --run` → 116/116 passed (10 test files)
- `npx tsc --noEmit` → passed
- `npm run build` → passed (67 modules, dist built)
- Mutation 1 (count all rows → badge shows wrong count) → FAILED as expected: `renders error rows honestly and not as source cards`
- Mutation 2 (show "Note saved" without note_id) → FAILED as expected: `does not show note saved confirmation when note_id is absent`
- Mutation 3 (render confidence value) → FAILED as expected: `does not render model confidence or score values from API response`
- Clean state restore → 18/18 tests passed

## Files modified
- `frontend/src/components/evidence/ToolCallCard.tsx` — deriveBadge error-row filter + honest note state
- `frontend/src/screens/ResearchAgent.test.tsx` — 3 new assertions + 1 new test (confidence rejection)