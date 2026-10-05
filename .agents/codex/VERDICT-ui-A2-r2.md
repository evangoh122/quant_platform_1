# Codex gpt-5.6-sol review round 2 — UI A2 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

- `frontend/src/components/tours/CoachMarks.tsx:164`: the spotlight clamp can produce a negative width when the measured target remains beyond the viewport’s right edge. For example, with `vw = 1024`, `rect.left = 1200`, and `rect.width = 100`, width becomes `min(116, 1024 - 1192) = -168`; the browser rejects that CSS width. A regression test added only to an archived `/tmp` copy failed (`NaN` computed style width). Clamp both rectangle edges before deriving a non-negative width/height.
- `frontend/src/components/tours/CoachMarks.test.tsx:377`: the test claiming a 360px viewport actually sets `innerWidth` to `1024`, so it does not cover the stated 360px scenario.

Validation:

- DeepSeek prerequisite: APPROVED
- Baseline Vitest: 60/60 passed
- TypeScript: passed
- Production build: passed
- Pure-updater mutation: correctly failed the StrictMode once-only test and emitted the React cross-component update warning
- Clamp-removal mutation: correctly failed both existing clamp tests
- Focus trap/restore, reduced-motion, resize/scroll, localStorage-failure, and existing 360px layout coverage passed
- Worktree unchanged
===VERDICT END===
