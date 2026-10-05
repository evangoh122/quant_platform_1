# BUILD-ui-A4: research agent redesign and evidence cards

Implement only A4 from `docs/ui_enhancement/PLAN.md`, after A3 has been
committed and checked.

## Numbered changes

1. Replace the raw JSON presentation in `frontend/src/screens/ResearchAgent.tsx`
   while continuing to call `api.chat(message)` and preserving the existing
   `/api/agent/chat` contract. Add the five known-good suggested questions,
   empty-input blocking, disabled send during submission, and preserve the
   question if the request fails.
2. Add the two-column conversation/execution layout. On narrow screens the
   evidence panel follows the answer. Add the question, grounded answer,
   follow-ups, saved-note confirmation, and clear unavailable/error states.
3. Add `frontend/src/components/ExecutionTrace.tsx` with only
   `pending | running | complete | failed | skipped` states derived from
   observed `ChatResponse.tool_calls` and `available`. Do not simulate timing,
   invent a trace ID, or claim a retrieval/model stage that the response does
   not support.
4. Add the exact evidence components under
   `frontend/src/components/evidence/`: `EvidencePanel.tsx`, `SourceCard.tsx`,
   `ToolCallCard.tsx`, `ProvenanceGrid.tsx`, and `DeveloperDetails.tsx`.
   Source cards show ticker, form, accession, accepted timestamp, section,
   source URL, and retrieval mode when those fields exist in nested SEC rows.
   Tool cards show typed status, ticker/source count where derivable, saved
   record ID, and Lakebase storage for a successful research-note write.
5. Keep raw `arguments` and `result` under a collapsed `Developer details`
   disclosure. Do not show them expanded by default. The response's narrow
   `sources[]` is not sufficient for all provenance fields; normalize the
   nested `tool_calls[].result.rows` shape with runtime guards and show `—`
   for absent fields.
6. Add tests for suggested question submission, answer rendering, SEC source
   card, failed tool, saved-note confirmation, collapsed developer details,
   send disabled during submit, empty input blocked, and API failure retaining
   the typed question. Add an explicit test that only observed tool stages are
   rendered.

## Tests that must fail on the current code

- `submits a suggested question and renders the grounded answer` — current
  agent has no suggested-question controls.
- `renders a typed SEC evidence card from nested result rows` — current UI
  renders generic JSON only.
- `renders failed tools as failed and saved notes with note id and Lakebase`
  — current UI has no typed cards or write confirmation.
- `keeps developer details collapsed by default` — current `ResearchAgent`
  expands a `<pre>` for every tool call.
- `disables send while submitting and blocks empty input` — current code
  disables only while sending and has no asserted empty-input affordance.
- `keeps the question after an API failure` — current code clears the input
  before the request and does not restore it.
- `does not render unsupported or simulated execution stages` — current code
  has no execution trace.

## Named mutations for DeepSeek

Run mutations for: expanding raw JSON by default; changing `ok: false` to a
success badge; dropping `accepted_ts`/`source_url` from a source card;
displaying a note without its `note_id`; adding simulated timer-based stages;
clearing the question before a failed request; allowing whitespace-only send;
and showing a model confidence score not present in the response. DeepSeek
must provide file:line evidence.

## Acceptance

Run:

```sh
cd frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build
```

Use LF line endings, do not touch `.agents/dispatch.sh`, commit the A4
changes, and write a MiMo verdict naming the commit and test results.

