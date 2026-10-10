# DeepSeek check — coach marks and Rag Workbench theme r2

Validate exact commit `a3c1236019a7e6a70b9050180ec34fa9d0f41273` read-only
(MiMo r2 build; binding request `.agents/requests/BUILD-coachmarks-rag-theme-r2.md`;
prior findings `.agents/deepseek/VERDICT-coachmarks-rag-theme-r1.md`).
MiMo's verdict is a self-report; reproduce evidence independently.

## Required review
1. Verify HEAD, clean tracked tree, ancestry from `origin/main`, scope limited to
   frontend + request/verdict artifacts.
2. Read the r2 request completely; inspect every changed production and test file.
3. Run `.agents/run-coachmarks-rag-theme-r2-check.sh` only via
   `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r2-check.sh`
   (no inline bash -c, PowerShell wrappers, UNC paths, Windows node). After one boundary failure stop and report FAILED.
4. Verify each of the 6 required product fixes and each of the 10 required regression tests in the r2 request: route-aware manual tour (agent/architecture/default), Analytics step navigates to the screen mounting `analytics-evidence` (System Health), fresh Agent screen has truthful `agent-evidence` anchor without fabricated evidence/write, `top|bottom|auto` placement honoring card height + viewport, bounded skip/defer for missing targets, 375px visibility/44px targets, replay with seen keys = 1, canonical tokens, no legacy light classes.
5. In isolated `git archive` copies (never git in a cp -r copy), re-run the mutation proofs MiMo claims; each must fail a relevant rendered/contract test for the intended reason, and the new tests must fail against r1 commit `8999a9c`/`7a0a77f`.
6. Legacy-style sweep: judge remaining hits (e.g. `ToolCallCard.tsx:36` blue "running" badge) — allowed only if genuinely semantic status color; otherwise CHANGES_REQUESTED. Also check ExecutionTrace, evidence cards, SymbolSelect, chart controls, status badges, OrderApprovalDrawer.
7. Missing/vacuous/surviving proof, production defect, or incomplete sweep => CHANGES_REQUESTED with file:line.

Write `.agents/deepseek/VERDICT-coachmarks-rag-theme-r2.md`; end with exactly:
`VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <full SHA or SHA_NOT_VERIFIED> | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r2.md`
