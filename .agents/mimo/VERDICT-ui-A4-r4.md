# VERDICT: ui-A4 — MiMo
**Status:** APPROVED
**Round:** 4

## Blocking findings
None.

## Non-blocking notes
- Added `include: ['src/**/*.{test,spec}.{ts,tsx}']` to vite.config.ts to prevent vitest scanning the entire Windows filesystem through WSL mount points. This is a build-infrastructure fix, not a feature change.
- The /tmp git archive copy cannot run tests standalone (no node_modules), which is expected for a fresh archive.

## Changes made
- `frontend/src/api/types.ts:118` — Removed invented `follow_ups?: string[]` from `ChatResponse` (backend `api/schemas.py:158-164` never returns it).
- `frontend/src/screens/ResearchAgent.tsx` — Removed `followUps` from `Message` interface, message construction, and follow-up questions UI block. Conversation is now a plain client-side list of turns, each calling `api.chat(message)`.
- `frontend/src/components/ExecutionTrace.tsx:11-44` — Replaced global `anyFailed` with per-stage failure derivation: `retrievalFailed` (from retrieval tools only) and `writeFailed` (from write tools only). A successful `search_sec_filings` + failed `save_research_note` now correctly shows Retrieval=Complete, Write=Failed.
- `frontend/src/components/ExecutionTrace.test.tsx` — New test file with 4 tests covering per-stage failure isolation (mutation: restore global anyFailed → fails).
- `frontend/src/screens/ResearchAgent.test.tsx` — Replaced follow-ups test with two-turn conversation test and failed-follow-up test (mutation: replace history with only latest turn → fails).
- `frontend/vite.config.ts` — Added `include` pattern for vitest.

## Checks run
- `npx vitest run src/components/ExecutionTrace.test.tsx src/screens/ResearchAgent.test.tsx` → 23 passed (4 + 19)
- `npx tsc --noEmit` → passed
- `npm run build` → passed (tsc + vite build, 67 modules, 1.90s)
- `git diff --check` → passed
- `git status` → clean (all changes committed)