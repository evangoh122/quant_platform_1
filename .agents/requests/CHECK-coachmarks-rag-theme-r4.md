# DeepSeek check — coach marks and Rag Workbench theme r4

Validate exact commit `bd73396a07fa97b60584efe8ef2d8f48086d0a19` read-only (MiMo r4; binding request `.agents/requests/BUILD-coachmarks-rag-theme-r4.md`; your prior verdict `.agents/deepseek/VERDICT-coachmarks-rag-theme-r3.md` was CHANGES_REQUESTED on 6a33f72 for B1: cross-screen tours reset to step 1 and restored the wrong screen). MiMo's evidence `.agents/mimo/EVIDENCE-coachmarks-rag-theme-r4.md` is a self-report; reproduce independently. Do not edit, commit, push, deploy or access credentials.

## Required review
1. HEAD, clean tracked tree (git status --porcelain --untracked-files=no), ancestry from origin/main, scope = frontend + artifacts only.
2. Run `.agents/run-coachmarks-rag-theme-r4-check.sh` ONLY via `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r4-check.sh`. One boundary failure => FAILED.
3. Confirm B1 is fixed in production (CoachMarks.tsx reset effect keyed on run edge only; initialScreenRef captured at run start; no stale-closure bug in currentScreenRef; handleClose restores the starting screen on Done, Skip, Escape and the X). Reproduce the cross-screen scenario yourself with a real stateful harness wired like App (onNavigate -> useState): the tour must reach the last step of every tour, step counter never returns to 1 after navigating, and the user ends on the starting screen, starting from a non-default screen.
4. Tests: the vacuous static-prop Test 16 must be gone; replacement is stateful; source-scan tests converted to rendered DOM/ARIA assertions; background inert asserted; Test 8 attribution accurate; commit message descriptive; r4 check script has no stale sentinel text and has the PATH/mnt boundary assertion.
5. In isolated `git archive` copies (never git in a cp -r copy) run: M1 put currentScreen back into the reset effect deps; M2 overwrite initialScreenRef each render; M3 remove inert from the drawer; M4 remove aria-controls on one disclosure; plus the r3 mutations (hardcode tour:'application' in AppShell, respect seen keys in TourHost, remove 44px rule, stale _v1 keys, blue badge, remove aria-expanded, remove skip link, drop Escape). Each must edit code (not comments) and fail a relevant rendered test for the intended reason. New tests must fail on r3 commit 6a33f72.
6. Any missing/vacuous/surviving proof or production defect => CHANGES_REQUESTED with file:line.

Write `.agents/deepseek/VERDICT-coachmarks-rag-theme-r4.md`; end with exactly:
`VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <full SHA or SHA_NOT_VERIFIED> | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r4.md`
