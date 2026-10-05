# BUILD-ui-A3: Platform Overview and Architecture & Tests

Implement only A3 from `docs/ui_enhancement/PLAN.md`, after A2 has been
committed and checked.

## Numbered changes

1. Add `frontend/src/screens/PlatformOverview.tsx` as the default landing
   screen. Use the exact hero copy from `OWNER_PLAN.md`, with actions to ask
   the research agent, explore market data, and view Architecture & Tests.
   Actions must navigate through the shell callback, not invent routes or
   change API contracts.
2. Add static evidence cards labelled exactly `Verified snapshot: 2026-10-05`
   for 287M+ records, 152.1M options records, 10,720 SEC embedding chunks,
   four third-party providers, the Lakebase operational model, and Spark
   bronze→silver→gold. These are snapshot claims, not live counters or API
   values. Do not add arbitrary confidence scores.
3. Add the compact responsive HTML/CSS stepper
   `External APIs → Spark ingestion → Delta bronze/silver/gold → AI retrieval
   → Lakebase action → Delta activity analytics`, plus eight rubric cards that
   link to the relevant screen/evidence. Use plain HTML/CSS; do not import
   React Flow or the old `PipelineFlow.tsx`.
4. Add `frontend/src/screens/ArchitectureEvidence.tsx`. Include the business
   workflow, the responsive technical diagram
   `Massive/SEC/CFTC/FRED → Spark → Delta bronze/silver/gold → FastAPI → React
   → AI agent → Lakebase → analytics_outbox → Spark analytics → Delta
   analytics`, the deterministic safety model, verified test groups with
   commit/date placeholders that are clearly not fabricated live counts, and
   known limitations: baseline signals only, DLT built not deployed, paper
   broker scaffold, and analytics require the refresh run.
5. Wire only the two new screens into the existing navigation handoff and add
   the architecture tour targets. Keep the existing signal screen's API and
   add the baseline label wherever it is presented; never call the 0.47 AUC a
   validated edge.
6. Add `frontend/src/screens/PlatformOverview.test.tsx` and
   `ArchitectureEvidence.test.tsx`. Test link/action navigation callbacks,
   snapshot labels, every required pipeline node, safety-model order,
   limitation copy, heading order, and responsive overflow-safe markup.

## Tests that must fail on the current code

- `renders Platform Overview as the landing content with snapshot labels` —
  current App defaults to Market Dashboard and has none of this content.
- `routes overview actions to agent, market, and architecture callbacks` —
  current App has no overview actions.
- `renders all six overview pipeline stages and eight rubric destinations` —
  current UI has no overview stepper/rubric cards.
- `renders the Architecture business workflow and deterministic safety model`
  — current UI has no Architecture & Tests screen.
- `labels baseline signals as a demonstration with no edge claimed` — current
  SignalExplorer has no baseline caveat.
- `does not render snapshot evidence as live counters` — a test should assert
  the snapshot label and absence of live API counter semantics.

## Named mutations for DeepSeek

Check mutations for: changing the landing route back to Market Dashboard;
removing the `Verified snapshot: 2026-10-05` label; presenting 287M+ as a
live count; omitting `analytics_outbox`; changing the safety order so the LLM
appears to execute directly; and replacing the baseline signal disclaimer
with validated-performance wording. DeepSeek must cite file:line evidence.

## Acceptance

Run:

```sh
cd frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build
```

Use LF line endings, do not touch `.agents/dispatch.sh`, commit the A3
changes, and write a MiMo verdict naming the commit and test results.

