# BUILD — PR #48 CodeRabbit repair round 2: effective regression proofs

You are MiMo. Work only on `feat/ui-enhancement` at or after
`17cf8eb037fb69e349ff96677ab8bde35c21fdd9`. Kimi validated the production
repairs but returned CHANGES_REQUESTED because three required regression tests
did not fail when their production fixes were mutated. Keep this round narrow.

## Required changes

1. `frontend/src/components/SymbolPicker.test.tsx`
   - Repair the delayed-blur regression test so blur occurs while the old prop
     is still rendered, the component is then rerendered with the new value,
     timers advance, and the input must retain the new value.
   - The unmodified test must fail when the blur callback uses the captured
     `value` instead of `valueRef.current`.

2. Agent-tour selector resolution
   - Add a test that imports `AGENT_TOUR`, renders the Research Agent screen,
     drives any state required to expose the note-confirmation target, and
     asserts every agent-tour selector resolves against that rendered screen.
   - Restoring the cross-screen `[data-tour="analytics-evidence"]` selector must
     fail this test.

3. Two-placeholder question replacement
   - Make the suggested-question builder directly testable without weakening
     encapsulation (a named export is acceptable).
   - Test an explicit template containing two `{SYMBOL}` occurrences and assert
     both are replaced.
   - Restoring first-occurrence-only replacement must fail this test.

4. `TourHost.tsx`
   - Prevent the delayed unseen-tour auto-start from replacing a manual
     `qp-tour-request` that arrives during the 600 ms window. Preserve the
     one-auto-start-per-mount and no-tour-chain behavior.
   - Add a fake-timer regression test: issue a manual tour request before the
     delay expires, advance beyond 600 ms, and assert the manual tour remains.

5. Clean up the indentation in `EvidencePanel.tsx` and remove or explicitly
   mark the now-unused `available` parameter in `ExecutionTrace.tsx` without
   changing behavior.

6. Correct `.agents/mimo/VERDICT-ui-pr48-coderabbit-r1.md` so it no longer
   falsely claims mutations 5, 8, and 11 were detected. Preserve the original
   record by clearly marking those three entries as superseded by r2 evidence.

## Required proofs

Use fresh `git archive` copies under `/tmp`. Each mutation must make its
targeted unmodified test fail:

1. Replace `valueRef.current` with the captured `value` in delayed blur.
2. Point an `AGENT_TOUR` step back to `[data-tour="analytics-evidence"]`.
3. Replace global symbol substitution with first-occurrence-only replacement.
4. Remove the manual-request protection from the delayed auto-start callback.

Do not copy production logic into tests or skip/xfail assertions.

## Acceptance

```bash
cd frontend
npx vitest --run
npx tsc --noEmit
npm run build
cd ..
git diff --check
```

Use LF endings. Do not touch dependencies, V1/V5, backend files,
`.agents/dispatch.sh`, deployment, or live data. Commit the intended changes on
`feat/ui-enhancement` and write
`.agents/mimo/VERDICT-ui-pr48-coderabbit-r2.md` with exact test output and the
four independent mutation failures. Do not push, merge, or comment on the PR.
