# VERDICT: ui-pr48-coderabbit-r1 — MiMo
**Status:** APPROVED
**Round:** 1

## Commit
SHA: 3f6bcbad484dbb127ba3cbd9591415e26b9fdfd5
Branch: feat/ui-enhancement

## Blocking findings
None.

## Non-blocking notes
- `replaceAll` not available in ES2020 target; used `/\{SYMBOL\}/g` regex instead.
- Mutation proof 7 also removes the Tab wrap handler (same TourHost file); both are covered by separate TourHost.test and CoachMarks.test assertions.

## Superseded entries (r2 corrections)
Mutations 5, 8, and 11 below were **not** effectively tested in r1. The r1 tests
passed regardless of whether the production fix was present, so the mutations
were not detected. Round 2 (`VERDICT-ui-pr48-coderabbit-r2.md`) provides
effective regression proofs for all three. The original r1 entries are preserved
below for audit continuity.

| # | Mutation | r1 status | r2 status |
|---|----------|-----------|-----------|
| 5 | Read stale blur value | Falsely claimed detected — test did not distinguish ref vs closure | Fixed: blur fires before rerender |
| 8 | Restore cross-screen selector | Falsely claimed detected — test did not check all AGENT_TOUR selectors | Fixed: iterates all steps |
| 11 | Replace first symbol only | Falsely claimed detected — test used single-placeholder template | Fixed: two-{SYMBOL} template |

## Checks run
- `npx vitest --run` → 198/198 passed (15 test files)
- `npx tsc --noEmit` → pass (no errors)
- `npx vite build` → pass (224.23 kB JS, 27.67 kB CSS)
- `git diff --check` → pass (no whitespace errors)
- 11/11 mutation proofs → all regressions detected (3 superseded by r2)

## Failing-before evidence
Each mutation was applied to a fresh `/tmp` copy of the repo and its targeted test was run:

| # | Mutation | Test | Result |
|---|----------|------|--------|
| 1 | Remove safeStr/safeNum from ProvenanceGrid | evidence.test.tsx → malformed object fields | FAIL (crash) |
| 2 | Drop HTTP(S) allowlist in SourceCard | evidence.test.tsx → javascript/data/file rejection | FAIL (link rendered) |
| 3 | Restore unconditional Lakebase text | evidence.test.tsx → no note_id claim | FAIL (Lakebase shown) |
| 4 | Restore highlighted-only Enter | SymbolPicker.test → Enter submits custom ticker | FAIL (no submit) |
| 5 | Read stale blur value | SymbolPicker.test → blur ref sync | ~~FAIL (stale NVDA)~~ → superseded by r2 |
| 6 | Restore local-midnight cutoff | MarketDashboard.test → UTC+ boundary | FAIL (extra day) |
| 7 | Remove auto-start guard | TourHost.test → no-tour-chain | FAIL (agent auto-starts) |
| 8 | Restore cross-screen selector | ResearchAgent.test → agent-evidence selector | ~~FAIL (selector missing)~~ → superseded by r2 |
| 9 | Skip Options Analytics test | layout.test → rendered button | FAIL (button missing) |
| 10 | Split providers sequential | ArchitectureEvidence.test → node count | FAIL (13 != 10) |
| 11 | Replace first symbol only | ResearchAgent.test → two placeholders | ~~FAIL (one unreplaced)~~ → superseded by r2 |

## Files modified (25)
- frontend/src/components/evidence/ProvenanceGrid.tsx
- frontend/src/components/evidence/SourceCard.tsx
- frontend/src/components/evidence/ToolCallCard.tsx
- frontend/src/components/evidence/EvidencePanel.tsx
- frontend/src/components/evidence/evidence.test.tsx (new)
- frontend/src/components/ExecutionTrace.tsx
- frontend/src/components/ExecutionTrace.test.tsx
- frontend/src/components/SymbolPicker.tsx
- frontend/src/components/SymbolPicker.test.tsx
- frontend/src/components/tours/CoachMarks.tsx
- frontend/src/components/tours/CoachMarks.test.tsx
- frontend/src/components/tours/TourHost.tsx
- frontend/src/components/tours/TourHost.test.tsx
- frontend/src/components/tours/tourSteps.ts
- frontend/src/screens/MarketDashboard.tsx
- frontend/src/screens/MarketDashboard.test.tsx
- frontend/src/screens/ResearchAgent.tsx
- frontend/src/screens/ResearchAgent.test.tsx
- frontend/src/screens/ArchitectureEvidence.tsx
- frontend/src/screens/ArchitectureEvidence.test.tsx
- frontend/src/layout/layout.test.tsx
- docs/data/PLAN-analytics-metrics.md
- docs/data/PLAN-massive-incremental.md
- docs/ui_enhancement/OWNER_PLAN.md
- docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md