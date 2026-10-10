# Build: repair coach marks and complete Rag Workbench theme (r2)

## Objective

Repair commit `8999a9cdb8c140b5ccb13e85b84d17ab5493e229` using the
independent DeepSeek findings in
`.agents/deepseek/VERDICT-coachmarks-rag-theme-r1.md`.

This is a corrective MiMo build. Do not deploy or start the stopped Databricks
app. Do not change backend/API behavior or dependencies.

## Required product fixes

1. Make the header `Take a tour` action route-aware:
   - `agent` screen -> Agent tour;
   - `architecture` screen -> Architecture tour;
   - every other screen -> Application tour.
   Test the real `qp-tour-request` event detail for all three cases.
2. Fix Application-tour Analytics navigation. The
   `[data-tour="analytics-evidence"]` target is owned by `SystemHealth`; the
   step must navigate to the screen that actually mounts that target. Do not
   point it at a placeholder screen.
3. Make the Agent tour work on a fresh Agent screen. A stable, truthful
   `[data-tour="agent-evidence"]` anchor must exist before any response, tool
   call, saved note, or Lakebase write. Do not fabricate evidence or a write.
4. Honor `placement: top | bottom | auto` in `CoachMarks`. Placement must
   account for measured card height and viewport collision; it may not always
   render as the current fixed bottom card.
5. Complete the Rag Workbench theme sweep. Remove old light-surface/action
   classes from every rendered screen and shared evidence/control component,
   including the exact residuals listed by DeepSeek (`PlatformOverview`,
   `ResearchAgent`, `SecFilingExplorer`, `SignalExplorer`, `SystemHealth`,
   `OrderApprovalDrawer`, evidence cards/panels, `ExecutionTrace`,
   `SymbolSelect`, chart controls and status badges). Semantic success,
   warning, and error colors may remain, but light `bg-white`, Slate surface,
   and Blue CTA styling must not remain as primary UI language.
6. Preserve navigation, focus, reduced-motion, mobile, data semantics, and all
   behavior already merged from PR #48.

## Regression tests required

Add behavior-based tests that fail against the defective r1 commit and prove:

1. Header manual-tour requests are route-aware for Agent, Architecture, and a
   default screen.
2. The Application tour navigates to the real Market, Agent, and System Health
   screens and obtains a visible, non-zero target for each selector-bearing
   step.
3. A fresh Agent screen exposes its evidence tour anchor with no response or
   saved note, without rendering fabricated evidence.
4. Architecture tour navigation mounts provenance and pipeline targets.
5. At 375 px the navigation target is visible, the card remains inside the
   viewport, and controls are at least 44x44 px.
6. `top`, `bottom`, and `auto` produce the declared placement behavior.
7. Missing targets use the bounded skip/defer policy and never silently render
   as an untargeted centered card.
8. Manual replay remains route-aware even when each seen key is `1`.
9. The canonical obsidian/silver/gold token values are present.
10. Rendered shared primitives and all rendered screens contain no old light
    surface/Blue CTA/Slate primary-surface classes.

Do not merely scan a hand-picked subset when the contract claims every
rendered screen. Use an enumerated screen/component matrix so additions are
visible in review.

## Required mutation proofs

Use isolated `git archive` copies. Each mutation must fail for the intended
assertion, and its exact command, exit code, and failure must be recorded:

- MUT1: remove cross-screen navigation from an Application step.
- MUT2: restore Agent evidence-anchor dependence on post-response content.
- MUT3: restore `--canvas: #f8fafc` or `--accent: #2563eb`.
- MUT4: restore a solid Blue/old active-navigation treatment.
- MUT5: restore one old light primary-surface class in a shared primitive and
  one in a rendered screen covered by the complete matrix.
- MUT6: ignore the `placement` option and force the card to the old fixed
  bottom position.

The pre-fix/failing-before proof must run against `8999a9c` (or its production
parent where appropriate) and fail for the intended behavior.

## Linux acceptance boundary

The native repository environment is WSL/Linux. Run Linux commands directly.
Never invoke `wsl.exe`, PowerShell, Windows Node/npm/npx, UNC paths, or Windows
wrappers.

Before counting frontend evidence, record and require:

```bash
uname -s                       # must print Linux
command -v node                # must not resolve under /mnt/
command -v npm                 # must not resolve under /mnt/
command -v npx                 # must not resolve under /mnt/
node -p 'process.platform'     # must print linux
```

If the worktree dependency cache is Windows-only or lacks Linux optional
packages, stop and report `FAILURE`; do not run `npm install`, alter the cache,
or fall back to Windows tooling.

Then run:

```bash
cd /home/jianj/code/qp1-rag-theme/frontend
npx vitest --run
npx tsc --noEmit
npm run build
cd ..
git diff --check origin/main...HEAD
```

Inspect the built output for the new tour keys and canonical palette.

## Scope and completion

- Frontend code/tests plus this request and MiMo verdict only.
- Preserve LF line endings.
- Commit every intended change on `feat/rag-workbench-theme`.
- Leave no unexpected files or tracked changes.
- Write `.agents/mimo/VERDICT-coachmarks-rag-theme-r2.md` with the Linux
  identity checks, files, exact SHA, failing-before evidence, acceptance
  commands, all six mutations, and scope audit.
- Emit exactly one terminal report after the evidence file is readable:

`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/rag-workbench-theme | evidence: .agents/mimo/VERDICT-coachmarks-rag-theme-r2.md`

`SUCCESS` is forbidden if any required test/mutation is absent, if any command
ran through Windows tooling, or if the reported SHA is not branch HEAD.
