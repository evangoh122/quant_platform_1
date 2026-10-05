# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — ui-A4 (saved by Claude)

===VERDICT START===

Status: CHANGES_REQUESTED

Blocking findings:

- `frontend/src/components/evidence/ProvenanceGrid.tsx:43-45` drops row-level errors instead of rendering `no_coverage`, `retrieval_unavailable`, `ticker_required`, and `unknown` honestly. `ToolCallCard.tsx:13-18` also counts error rows as sources.
- `frontend/src/components/evidence/ToolCallCard.tsx:10-12` survived the `ok: false → success` mutation because tests only detect “Failed” from `ExecutionTrace`, not the tool card.
- `frontend/src/components/evidence/ToolCallCard.tsx:27-31` and `ResearchAgent.tsx:92-95` claim a note was saved without requiring `note_id`.
- `frontend/src/components/evidence/EvidencePanel.tsx:12-21` hides unavailable-agent state when there are no tool calls.
- Required follow-up rendering is absent from `ResearchAgent.tsx`.

Mutation results:

- Raw JSON expanded: killed.
- `ok: false` success badge: SURVIVED.
- Dropped `accepted_ts`/`source_url`: killed.
- Simulated stages: killed.
- Cleared failed-request question: killed.
- Whitespace-only send: killed.
- Confidence score: no fabricated score present.

Checks:

- Existing suite before `npm ci`: 110/110 passed.
- TypeScript and build passed.
- Exact `npm ci` rerun failed with environment `EPERM` while spawning esbuild.

===VERDICT END===
