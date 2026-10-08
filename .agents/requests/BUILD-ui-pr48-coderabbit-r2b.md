# BUILD — PR #48 round 2b: finish interrupted r2 validation and commit

You are MiMo. Resume the existing uncommitted r2 work on
`feat/ui-enhancement` at or after `17cf8eb037fb69e349ff96677ab8bde35c21fdd9`.
Do not discard or redo the working-tree changes. The prior dispatch timed out
while validating them.

## Required completion

1. Review the uncommitted diff against
   `.agents/requests/BUILD-ui-pr48-coderabbit-r2.md`; correct any incomplete or
   out-of-scope change.
2. Preserve the three already-demonstrated mutation failures:
   stale blur value, cross-screen tour selector, and missing manual-request
   guard.
3. Correctly apply the remaining mutation in a fresh `git archive` copy:
   change the global `{SYMBOL}` replacement back to first-occurrence-only.
   Prove the new explicit two-placeholder test fails. A mutation command that
   did not alter the target file is not evidence.
4. Run frontend commands from WSL with the Linux Node/NVM path, not Windows
   `npx` through a UNC working directory:

```bash
cd frontend
npx vitest --run
npx tsc --noEmit
npm run build
cd ..
git diff --check
```

5. Ensure edited text files end with LF newlines.
6. Commit the intended r2 changes and write
   `.agents/mimo/VERDICT-ui-pr48-coderabbit-r2.md` with exact acceptance output
   and all four real mutation failures. Clearly supersede the three false r1
   mutation claims without rewriting history.

Do not touch dependencies, backend files, V1/V5, `.agents/dispatch.sh`,
deployment, or live data. Do not push, merge, or comment on the PR.
