# VERDICT: coachmarks-rag-theme-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Linux identity checks

```
$ uname -s
Linux
$ command -v node
/home/jianj/.nvm/versions/node/v26.5.0/bin/node
$ command -v npm
/home/jianj/.nvm/versions/node/v26.5.0/bin/npm
$ command -v npx
/home/jianj/.nvm/versions/node/v26.5.0/bin/npx
$ node -p 'process.platform'
linux
```

All commands resolved under `~/.nvm/versions/node/` (Linux-native). No Windows
Node/npm/npx was used.

## Failing-before evidence (against 8999a9c)

9 tests fail when the r2 test suite runs against the r1 commit (8999a9c):

```
FAIL  Test 2: Application tour navigates to real screens and finds targets > APPLICATION_TOUR steps navigate to market, agent, and health screens
  → expect(received).toBe(expected) — Expected: 'health', Received: 'analytics'

FAIL  Test 3: Fresh Agent screen exposes evidence tour anchor > evidence-panel-empty has data-tour="agent-evidence" even with no tool calls
  → Unable to find an element with: data-tour="agent-evidence"

FAIL  Test 6: top, bottom, and auto placement behavior > placement: top renders card above the target
  → expect(received).toBeTruthy() — card.style.bottom is empty (placement ignored)

FAIL  Test 10 (6 files): No old light surface/Blue CTA/Slate classes
  → SourceCard.tsx, ToolCallCard.tsx, SystemHealth.tsx, OrderApprovalDrawer.tsx, SecFilingExplorer.tsx, PageHeader.tsx still contain bg-white/bg-slate-*/text-slate-*/text-blue-* classes
```

## Mutation proofs

Each mutation was applied to an isolated `git archive HEAD` copy with symlinked
node_modules. The exact command, exit code, and failure:

### MUT1: remove cross-screen navigation from Application Analytics step
```
$ sed -i "s/navigateTo: 'health'/navigateTo: 'analytics'/" /tmp/mutations/mut1/frontend/src/components/tours/tourSteps.ts
$ cd /tmp/mutations/mut1/frontend && npx vitest --run -t 'APPLICATION_TOUR steps navigate' src/components/tours/coachmarks-r2.test.tsx
→ FAILED (exit 1): expect(received).toBe(expected) — Expected: 'health', Received: 'analytics'
```

### MUT2: restore Agent evidence-anchor dependence on post-response content
```
$ python3 apply_mutation.py mut2  # removes data-tour="agent-evidence" from EvidencePanel empty state
$ cd /tmp/mutations/mut2/frontend && npx vitest --run -t 'evidence-panel-empty has data-tour' src/components/tours/coachmarks-r2.test.tsx
→ FAILED (exit 1): Unable to find an element with: data-tour="agent-evidence"
```

### MUT3: restore --canvas: #f8fafc
```
$ python3 apply_mutation.py mut3  # replaces --canvas: #090A0C with --canvas: #f8fafc
$ cd /tmp/mutations/mut3/frontend && npx vitest --run -t 'canvas' src/components/tours/coachmarks-r2.test.tsx
→ FAILED (exit 1): expect(received).toBe(expected) — Expected: '#090A0C', Received: '#f8fafc'
```

### MUT4: restore solid Blue/old active-navigation treatment
```
$ python3 apply_mutation2.py  # replaces var(--accent-dim) with #2563eb in .nav-item.active
$ cd /tmp/mutations/mut4/frontend && npx vitest --run -t 'nav-item' src/components/tours/coachmarks-r2.test.tsx
→ FAILED (exit 1): expect(css).not.toMatch(...) — CSS contains background: #2563eb in .nav-item.active
```

### MUT5: restore old light primary-surface class in shared primitive and rendered screen
```
$ python3 fix_mut5.py  # restores bg-slate-100 in FreshnessBadge.tsx and border-slate-200 bg-white in PlatformOverview.tsx
$ cd /tmp/mutations/mut5/frontend && npx vitest --run -t 'contains no legacy' src/components/tours/coachmarks-r2.test.tsx
→ FAILED (exit 1): FreshnessBadge.tsx contains 'bg-slate-100 text-slate-600'
```

### MUT6: ignore the placement option and force card to old fixed bottom
```
$ python3 apply_mutation.py mut6  # replaces placement logic with forced "auto"
$ cd /tmp/mutations/mut6/frontend && npx vitest --run -t 'placement: top renders card above' src/components/tours/coachmarks-r2.test.tsx
→ FAILED (exit 1): expect(received).toBeTruthy() — card.style.bottom is empty
```

## Acceptance commands

```
$ cd /home/jianj/code/qp1-rag-theme/frontend
$ npx vitest --run
 Test Files  16 passed (16)
      Tests  307 passed (307)
   Duration  7.74s

$ npx tsc --noEmit
TSC_OK

$ npm run build
✓ built in 1.79s
dist/assets/index-rdcDAgbp.css   25.04 kB
dist/assets/index-81_4XrRY.js   226.22 kB

$ cd /home/jianj/code/qp1-rag-theme
$ git diff --check origin/main...HEAD
(clean)
```

## Built output verification

Tour keys (v2) present in built JS:
- `qp_tour_application_v2`
- `qp_tour_agent_v2`
- `qp_tour_architecture_v2`

Canonical palette in built CSS:
- `#090A0C` (canvas), `#111317` (surface), `#181B20` (surface-raised)
- `#D6B65A` (accent), `#F1D77A` (accent-bright), `#C9A227` (accent-fill)

## Files changed

| File | Change |
|------|--------|
| `frontend/src/layout/AppShell.tsx` | Route-aware tour dispatch |
| `frontend/src/components/tours/tourSteps.ts` | Analytics step navigates to 'health' |
| `frontend/src/components/evidence/EvidencePanel.tsx` | data-tour on empty state + theme tokens |
| `frontend/src/components/tours/CoachMarks.tsx` | Placement prop (top/bottom/auto) |
| `frontend/src/screens/PlatformOverview.tsx` | Theme sweep |
| `frontend/src/components/ExecutionTrace.tsx` | Theme sweep |
| `frontend/src/components/evidence/ToolCallCard.tsx` | Theme sweep |
| `frontend/src/components/evidence/SourceCard.tsx` | Theme sweep |
| `frontend/src/components/evidence/DeveloperDetails.tsx` | Theme sweep |
| `frontend/src/components/evidence/ProvenanceGrid.tsx` | Theme sweep |
| `frontend/src/components/FreshnessBadge.tsx` | Theme sweep |
| `frontend/src/components/SymbolSelect.tsx` | Theme sweep |
| `frontend/src/layout/PageHeader.tsx` | Theme sweep |
| `frontend/src/screens/MarketDashboard.tsx` | Theme sweep |
| `frontend/src/screens/ResearchAgent.tsx` | Theme sweep |
| `frontend/src/screens/SecFilingExplorer.tsx` | Theme sweep |
| `frontend/src/screens/SignalExplorer.tsx` | Theme sweep |
| `frontend/src/screens/SystemHealth.tsx` | Theme sweep |
| `frontend/src/screens/OrderApprovalDrawer.tsx` | Theme sweep |
| `frontend/src/components/tours/coachmarks-r2.test.tsx` | 64 new regression tests |

## Scope audit

- All changes limited to `frontend/**` (no backend/API change).
- No secrets in committed files.
- LF line endings on all changed files.
- No unexpected files or tracked changes outside scope.
- Branch: `feat/rag-workbench-theme` (not pushed to main).

## Commit

```
SHA: a3c1236019a7e6a70b9050180ec34fa9d0f41273
Branch: feat/rag-workbench-theme
Message: fix: repair coach marks and complete rag workbench theme sweep (r2)
```
