# DeepSeek check — coach marks and Rag Workbench theme r3

Validate exact commit `6a33f723a399681d5f1294044a401a7f4a53af0b` read-only (MiMo r3; binding request `.agents/requests/BUILD-coachmarks-rag-theme-r3.md`; prior failure `.agents/deepseek/VERDICT-coachmarks-rag-theme-r2.md`). MiMo's evidence is a self-report; reproduce independently. Do not edit, commit, push, deploy or access credentials. Note: commit message is only "fix:" — report it as a non-blocking note.

## Required review
1. Verify HEAD, clean tracked tree, ancestry from origin/main, scope limited to frontend + artifacts.
2. Read the r3 request completely (Part A: r2 repairs F1-F4 + blue badge; Part B: items 1-7). Inspect every changed production and test file.
3. Run `.agents/run-coachmarks-rag-theme-r3-check.sh` ONLY via `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r3-check.sh`. One boundary failure => FAILED.
4. Part A: confirm tests now render the REAL AppShell/App (no re-implemented harness), assert real `qp-tour-request` detail for agent/architecture/default; seen-key=1 replay exercised via real constants; 375px test asserts nav-target visibility, card in viewport and 44x44 controls with real assertions (not toBeTruthy); App.test uses current versioned keys and asserts dispatched tour; ToolCallCard blue badge replaced, plus a legacy-class test.
5. Part B: skip link + main target; labelled research input; mobile drawer modal (Escape, focus containment, focus restored, background inert — verify inert is actually applied); aria-expanded/aria-controls referencing real ids on EVERY collapsible evidence disclosure (grep for other disclosures); ArchitectureEvidence no unbacked "Verified"; missing-target explicit state in a polite live region; screen-change announcement; tour exit restores original screen.
6. In isolated `git archive` copies (never git in a cp -r copy) re-run the mutations the evidence claims (incl. hardcoding `tour:'application'` in AppShell.tsx, removing aria-expanded, removing the skip link, dropping Escape handling, removing restore-screen); each must fail a relevant rendered test for the intended reason. New tests must fail on r2 commit a3c1236.
7. Missing/vacuous/surviving proof or production defect => CHANGES_REQUESTED with file:line.

Write `.agents/deepseek/VERDICT-coachmarks-rag-theme-r3.md`; end with exactly:
`VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <full SHA or SHA_NOT_VERIFIED> | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r3.md`
