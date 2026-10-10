# DeepSeek check — coach marks and Rag Workbench theme r5

Validate exact commit `970c4b49fb92606d6becda502847c1035f71ebca` read-only (MiMo r5; binding request `.agents/requests/BUILD-coachmarks-rag-theme-r5.md`; Codex final validation of r4 (bd73396) was CHANGES_REQUESTED: CoachMarks.tsx used a hardcoded 180px / 200px for auto placement and ignored collision for explicit top/bottom; you approved r4 and missed it, so be especially thorough on placement). MiMo's evidence `.agents/mimo/EVIDENCE-coachmarks-rag-theme-r5.md` is a self-report; reproduce independently. Do not edit, commit, push, deploy or access credentials.

## Required review
1. HEAD, clean tracked tree (git status --porcelain --untracked-files=no), ancestry from origin/main, scope frontend + artifacts only.
2. Run `.agents/run-coachmarks-rag-theme-r5-check.sh` ONLY via `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r5-check.sh`. One boundary failure => FAILED.
3. Verify placement in production (CoachMarks.tsx ~lines 325-355): the card height is MEASURED (layout effect, re-measured on step/content/viewport change, not a one-time guess), fallback is a named constant, auto/top/bottom flip and clamp correctly for short and tall cards and targets near top/middle/bottom, the card is always fully inside the viewport (top >= margin, bottom <= vh - margin), the 'above' branch positions with bottom correctly, horizontal clamp holds, and there is no render loop or stale-height bug (measure -> setState -> re-render -> measure). Check what happens on first render before measurement and on window resize.
4. Tests must stub measured height via the real card element (not copy production logic), cover heights {120,320} and top/middle/bottom targets for auto, top, bottom, and prove the same target picks a different side when the card height changes. Verify they would fail on the r4 commit bd73396.
5. In isolated `git archive` copies (never git in a cp -r copy) run M1 hardcode height, M2 bottom never flips, M3 remove final viewport clamp, M4 swap top/bottom branches, plus the r4 mutations (currentScreen back into reset deps, overwrite initialScreenRef, remove inert, remove aria-controls, hardcode tour application, remove aria-expanded). Each mutation edits code (not comments) and must fail a relevant rendered test for the intended reason.
6. Missing/vacuous/surviving proof or production defect => CHANGES_REQUESTED with file:line.

Write `.agents/deepseek/VERDICT-coachmarks-rag-theme-r5.md`; end with exactly:
`VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <full SHA or SHA_NOT_VERIFIED> | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r5.md`
