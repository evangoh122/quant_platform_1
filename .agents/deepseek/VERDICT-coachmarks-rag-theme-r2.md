# VERDICT: coachmarks-rag-theme-r2 — DeepSeek
**Status:** FAILED
**Round:** 2

## Scope / git audit (request item 1)

- HEAD `a3c1236019a7e6a70b9050180ec34fa9d0f41273` matches the required SHA. ✓
- `git merge-base --is-ancestor origin/main HEAD` → pass. ✓
- `git status --porcelain --untracked-files=no` → empty (tracked tree clean). ✓
- `git diff --check origin/main...HEAD` → clean. ✓
- r2 delta (`8999a9c...HEAD`) limited to `frontend/**` + `.agents/requests/BUILD-coachmarks-rag-theme-r2.md`
  + `.agents/deepseek/VERDICT-coachmarks-rag-theme-r1.md` (23 files). No backend/API change. ✓
- Untracked check-phase artifacts present (not committed, not part of `a3c1236`):
  `.agents/mimo/VERDICT-coachmarks-rag-theme-r2.md`, `.agents/requests/CHECK-coachmarks-rag-theme-r2.md`,
  `.agents/run-coachmarks-rag-theme-r2-check.sh`. Not blocking (ignored by the check script's
  `--untracked-files=no`), noted for completeness.

## Blocking findings

### B1. Acceptance is still not reproducible through the sanctioned bridge (boundary failure)
The mandated command
`wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r2-check.sh`
does **not** run the frontend checks with Linux Node — identical to r1 B1.

Non-interactive `bash` in this environment does not have Linux Node on `PATH`:

```
$ command -v node   → (empty — not found)
$ command -v npm    → /mnt/c/Program Files/nodejs/npm   (Windows, under /mnt/)
$ command -v npx    → /mnt/c/Program Files/nodejs/npx   (Windows, under /mnt/)
```

The check script relies on bare `npx tsc --noEmit` (`.agents/run-coachmarks-rag-theme-r2-check.sh:9`)
and does **not** source nvm, so `npx` resolves to the Windows binary. The run then launched
Windows `tsc` via `CMD.EXE`, which cannot handle the UNC working directory:

```
'\\wsl.localhost\Ubuntu\home\jianj\code\qp1-rag-theme\frontend'
CMD.EXE was started with the above path as the current directory.
UNC paths are not supported.  Defaulting to Windows directory.
Version 5.9.3
tsc: The TypeScript Compiler - Version 5.9.3   (…help text, not a compile…)
```

`set -euo pipefail` (`run-coachmarks-rag-theme-r2-check.sh:2`) halted the script at the `npx tsc`
step; the output never reaches `vitest`/`npm run build` and never prints the sentinel
`r2 check script finished` (line 14). Exit code is non-zero.

This violates the request's Linux acceptance boundary (must resolve `node`, and `npm`/`npx`
must not resolve under `/mnt/`, `process.platform` must be `linux`) and the hard rule that
Windows Node/UNC must never be used. MiMo's self-reported identity block (Linux `node` at
`~/.nvm/versions/node/v26.5.0/bin/node`, `243`/`307` passing tests) is **not** reproducible via
the sanctioned bridge because nvm is only sourced in interactive shells — the exact failure mode
r1 flagged and r2 was meant to fix. Per request item 3, after one boundary failure the verdict
is FAILED.

## Additional findings (must be addressed before re-approval; already force CHANGES_REQUESTED)

### F1. Route-aware tests are vacuous — they test a re-implementation, not `AppShell`
`frontend/src/components/tours/coachmarks-r2.test.tsx:168-178` defines `AppShellTourTest`, a
harness that re-implements the route-selection ternary verbatim, and Test 1 (lines 123-165) and
Test 8 (lines 433-473) click *that* harness. They never render the real
`frontend/src/layout/AppShell.tsx:42-45`. A revert of `AppShell.tsx` to hardcode
`tour: 'application'` would pass Test 1 and Test 8 unchanged — the proof "survives" the defect.
The request item 1 requires "Test the real `qp-tour-request` event detail for all three cases";
this is not satisfied.

### F2. Test 8 is additionally a no-op on its stated premise
Test 8 seeds `mockStore[APPLICATION_TOUR_KEY] = '1'` etc. (lines 439-441, 457-459) but the
`AppShellTourTest` harness never reads localStorage, and route selection in production
(`AppShell.tsx:43`) is independent of seen keys. The "seen key = 1" seeding does not exercise
any production behavior; the test merely repeats Test 1.

### F3. 375 px / 44 px test does not actually assert visibility or control size
`coachmarks-r2.test.tsx:252-291` (Test 5) asserts card width (`<= vw-24`, `> 0`) but:
- "navigation target is visible" is never asserted (no viewport-collision check on `navTarget`).
- "controls at least 44×44" is reduced to `expect(btn).toBeTruthy()` (line 287); the CSS
  `@media` rule at `frontend/src/index.css:120` is referenced in a comment but never read or
  asserted, so requirement #5 is unmet.

### F4. No real-App route-aware replay coverage; stale `_v1` keys remain
`frontend/src/App.test.tsx:153-155` still seeds `qp_tour_application_v1` / `qp_tour_agent_v1` /
`qp_tour_architecture_v1` (stale `_v1` keys) and its "Take a tour" tests (lines 151-193) assert
only that a dialog opens, never the dispatched `tour` value. Combined with F1, the route-aware
dispatch in production is untested by any test that renders the real `AppShell`/`App`.

## Checks run

- `git rev-parse HEAD` → `a3c1236019a7e6a70b9050180ec34fa9d0f41273` (pass)
- `git merge-base --is-ancestor origin/main HEAD` → pass
- `git status --porcelain --untracked-files=no` → clean
- `git diff --check origin/main...HEAD` → clean
- `command -v node` → empty (Linux Node absent in non-interactive shell) — boundary fail
- `command -v npm` → `/mnt/c/Program Files/nodejs/npm` — boundary fail
- `command -v npx` → `/mnt/c/Program Files/nodejs/npx` — boundary fail
- Sanctioned bridge:
  `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-rag-theme/.agents/run-coachmarks-rag-theme-r2-check.sh`
  → FAILED (Windows `CMD.EXE` invoked; UNC path unsupported; Windows `tsc` printed help; frontend
  suite never ran; non-zero exit).

VALIDATION DONE | verdict: FAILED | sha: a3c1236019a7e6a70b9050180ec34fa9d0f41273 | evidence: .agents/deepseek/VERDICT-coachmarks-rag-theme-r2.md
