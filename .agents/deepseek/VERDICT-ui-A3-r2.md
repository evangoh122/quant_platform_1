===VERDICT START===
# VERDICT: ui-A3-r2 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 2

## Summary

Commit `b9c3c59` fixes the round-1 blocking finding's *letter*: the `SignalExplorer` disclaimer now
renders dynamic `model_version`/`horizon` from loaded rows and the fixed caveat
"no validated trading edge claimed" is mounted and asserted in loaded/empty/error states. The
"validated wording" mutation is caught (3/4 SignalExplorer tests fail). Every A3 r1 named mutation
and all A1/A2 named mutations still fail their guards. `tsc` and `vite build` are clean.

However, the round-2 spec's second half — *"Never show an AUC that is not in the data"* and *"do not
hardcode a model version or AUC"* (`BUILD-ui-A3-r2.md` item 1) — is **not enforced by any test**.
Re-hardcoding either an AUC or a model version into the disclaimer survives 95/95. The exact defect
this fix removed is therefore unprotected against silent regression.

## Blocking findings

- [frontend/src/screens/SignalExplorer.test.tsx:49-108] No test asserts the *absence* of a hardcoded
  AUC or hardcoded model version in the disclaimer. The four tests only assert *presence* of the
  caveat and of the mocked `baseline-logreg-v1-1d`. Two spec-forbidden mutations survive untouched
  (verified in fresh `git archive HEAD | tar -x -C /tmp/qp1-r2-check` copies):
  - Insert `hold-out AUC 0.47` after `<strong>Baseline demonstration</strong>` (`SignalExplorer.tsx:39`)
    → `Tests 95 passed (95)`. Spec `BUILD-ui-A3-r2.md:1` "Never show an AUC that is not in the data"
    → no failure.
  - Insert `model baseline-logreg-v0-2026-10-05` (the pre-PR-#40 version) in the same place → `Tests
    95 passed (95)`. Spec `BUILD-ui-A3-r2.md:1` "do not hardcode a model version or AUC" → no failure.
  A regression re-introducing the r1 hardcoded AUC/model-version would pass CI silently.

## Named mutations (all run in fresh archive copies, WSL node v26.5.0)

A3 round 2:
- Caveat → "This is a validated trading signal with a proven statistical edge." → **3 failed**
  (caught: `SignalExplorer.test.tsx` loaded/empty/error disclaimer tests).
- Hardcode `hold-out AUC 0.47` → **0 failed (SURVIVES — blocking)**.
- Hardcode `model baseline-logreg-v0-2026-10-05` → **0 failed (SURVIVES — blocking)**.

A3 round 1 (re-run):
- Landing route → Market Dashboard (`App.tsx:79` `'market'`) → **24 failed**.
- Snapshot date `2026-10-05` → `2026-10-06` (`PlatformOverview.tsx:7`) → **2 failed**.
- 287M+ presented as "Live count" (`PlatformOverview.tsx:98`) → **1 failed**.
- Omit `analytics_outbox` (`ArchitectureEvidence.tsx:14`) → **2 failed**.
- Safety order → "LLM executes write" (`ArchitectureEvidence.tsx:23`) → **2 failed**.

A1 (re-run):
- Remove `wasOpen.current &&` focus guard (`MobileNavigation.tsx:39`) → **1 failed**.
- Remove `aria-modal="true"` (`MobileNavigation.tsx:84`) → **1 failed**.
- Remove collapsed `aria-label` (`Sidebar.tsx:50`) → **1 failed**.
- `min-w-[400px]` shell root (`AppShell.tsx:51`) → **1 failed**.
- Remove "Options Analytics" from NAV_GROUPS (`App.tsx:38`) → **2 failed**.

A2 (re-run):
- Unversion tour keys (`tourSteps.ts:3-5`) → **4 failed**.
- Remove `markTourSeen(tour.key)` (`TourHost.tsx:35`) → **3 failed**.
- Missing selector blocks Next (`CoachMarks.tsx:95`) → **1 failed**.
- Remove focus restore (`CoachMarks.tsx:91`) → **2 failed**.
- ArrowLeft wraps to last step (`CoachMarks.tsx:102`) → **1 failed**.
- Remove reduced-motion guard (`TourHost.tsx:54`) → **1 failed**.
- Drop resize/scroll listeners (`CoachMarks.tsx:76-77`) → **2 failed**.

## Checks run

- `npx vitest --run` (baseline, clean archive copy) → **95/95 pass** (9 files).
- `npx tsc --noEmit` → **pass** (exit 0).
- `npm run build` → **pass** (60 modules; 200.22 kB JS / 24.36 kB CSS).
- `git status --short` (worktree) → clean; all mutations run in `/tmp` copies only.

## Non-blocking notes

- `frontend/src/screens/ArchitectureEvidence.tsx:56` still hardcodes the pre-PR-#40 copy
  "baseline-logreg-v0-2026-10-05 … hold-out AUC 0.47" in its Known Limitations list (asserted by
  `ArchitectureEvidence.test.tsx:67-68`). This is a static evidence screen out of the r2 scope
  (`SignalExplorer.tsx:38-41`), but it is stale relative to the PR-#40 republish as
  `baseline-logreg-v1-1d` and is worth a follow-up wording pass.
- The disclaimer's `model_version`/`horizon` presence assertions (`SignalExplorer.test.tsx:62-63`)
  would also pass via the table's "Model"/"Horizon" columns, so they do not specifically prove the
  value is rendered *inside the disclaimer*; the caveat-text tests are the strong guard.
- `b9c3c59` also (accidentally) committed `docs/data/PLAN-massive-incremental.md` — a Codex plan
  doc, not code; ignored per instructions.
===VERDICT END===
