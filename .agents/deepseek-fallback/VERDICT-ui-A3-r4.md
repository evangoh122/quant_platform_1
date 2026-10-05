# Checker: Codex gpt-5.6-luna (DeepSeek out of balance) — ui-A3-r4 (saved by Claude)

===VERDICT START===
Status: APPROVED

Evidence:
- `frontend/src/screens/ArchitectureEvidence.tsx:56` uses the required baseline wording; stale AUC/model text is absent.
- `frontend/src/screens/ArchitectureEvidence.tsx:119-130` renders 13 ordered pipeline nodes.
- `frontend/src/screens/ArchitectureEvidence.test.tsx:51-64,91-94` verifies ordering and accessibility.
- Vitest: 97/97 passed; `tsc --noEmit` and build passed.
- All A3/A1/A2 mutations failed as required, including fresh archive-copy checks.
- Working tree is clean.
===VERDICT END===
