# VERDICT: ui-A4-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings addressed

1. **ProvenanceGrid.tsx:43-45 + ToolCallCard.tsx:13-18** — Error rows (`no_coverage`, `retrieval_unavailable`, `ticker_required`, `unknown`) now render honestly via `errorLabel()` at `ProvenanceGrid.tsx:30-41` and are displayed as amber alert boxes (`data-testid="provenance-error"`) at `ProvenanceGrid.tsx:78-85`, never as `SourceCard`. `deriveSourceCount` at `ToolCallCard.tsx:57-64` now filters out error rows before counting.
   - **Mutation: render error rows as SourceCards → FAIL.** Test `renders error rows honestly and not as source cards` asserts exactly 1 `source-card` for the good row; error row rendered as `provenance-error` instead.

2. **ToolCallCard.tsx:10-12** — `ok:false` already returned `{ label: 'Failed', cls: 'bg-red-100 ...' }` at line 10-12. Added targeted test `shows Failed badge on tool card when ok is false` that asserts the `tool-call-0` element contains text "Failed" AND has a `.bg-red-100` badge child (not just ExecutionTrace).
   - **Mutation: ok:false → success badge → FAIL.** Test queries `tool-call-0` for `Failed` text and red badge class.

3. **ToolCallCard.tsx:27-31 + ResearchAgent.tsx:92-95** — "Research note saved to Lakebase" now gated on `note_id` presence: `ToolCallCard.tsx:107` (`toolCall.ok && noteId`) and `ResearchAgent.tsx:92` (`tc.ok && tc.result?.note_id`). Badge at `ToolCallCard.tsx:27-35` shows amber "Note saved" (without note_id) vs emerald "Note {id}" (with note_id).
   - **Mutation: drop note_id requirement → FAIL.** Test `does not show note saved confirmation when note_id is absent` asserts `queryByText(/Research note saved to Lakebase/)` returns null.

4. **EvidencePanel.tsx:12-21** — Agent-unavailable alert now renders inside the `evidence-panel-empty` state when `!available`, at `EvidencePanel.tsx:17-23`.
   - **Mutation: hide unavailable state when no tool calls → FAIL.** Test `shows agent-unavailable state when available is false and no tool calls` asserts `getByRole('alert')` matches `/Agent tools are unavailable/`.

5. **Follow-up rendering** — Added `follow_ups?: string[]` to `ChatResponse` type at `types.ts:117`. ResearchAgent renders follow-up buttons when `m.followUps.length > 0` at `ResearchAgent.tsx:97-112`. Test `renders follow-up questions when API returns them` verifies buttons appear and clicking one submits a second request.

## Checks run

- `npx vitest --run` → 115/115 passed (10 test files)
- `npx tsc --noEmit` → clean
- `npm run build` → success (67 modules, 212.25 kB JS)

## Commits

- `d7e0400` — ProvenanceGrid error rows + ToolCallCard source count filter
- `970ef34` — EvidencePanel agent-unavailable in empty state
- `b331f27` — ResearchAgent note_id gate + follow_ups type
- `c50e3bf` — Mutation-killing tests for all 5 fixes