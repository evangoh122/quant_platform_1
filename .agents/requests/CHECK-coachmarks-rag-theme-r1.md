# DeepSeek check — coach marks and Rag Workbench theme r1

Validate exact commit `8999a9cdb8c140b5ccb13e85b84d17ab5493e229`
read-only. MiMo's verdict is a self-report and omits the required failing-before
and mutation transcripts; reproduce the evidence independently.

## Required review

1. Verify exact HEAD, clean tracked worktree, ancestry from `origin/main`, and
   scope limited to frontend plus request/verdict artifacts.
2. Read the binding request
   `.agents/requests/BUILD-coachmarks-rag-theme-r1.md` completely and inspect
   every changed production and test file.
3. Run full acceptance through the repository-owned LF script
   `.agents/run-coachmarks-rag-theme-check.sh` using only the sanctioned bridge:
   `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-check.sh`.
   Do not use inline `bash -c`/`-lc`, PowerShell wrappers, UNC paths, or Windows
   Node/npm/npx. After one boundary failure, stop and report FAILED.
4. In isolated `git archive` copies, reproduce the request's failing-before
   evidence and MUT1–MUT5. Each mutation must fail a relevant rendered or
   contract test for the intended reason; no copied production logic.
5. Specifically verify cross-screen target navigation, bounded missing-target
   handling, fresh Agent tour without `lakebase-write`, route-aware manual
   replay, mobile 375 px behavior, placement semantics, canonical palette,
   semantic shared primitives, and accessible active navigation.
6. Treat any missing/vacuous/surviving proof, production defect, or incomplete
   palette/screen sweep as `CHANGES_REQUESTED` with file:line evidence.

Write `.agents/deepseek/VERDICT-coachmarks-rag-theme-r1.md` and end with:

`VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <full SHA or SHA_NOT_VERIFIED> | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r1.md`
