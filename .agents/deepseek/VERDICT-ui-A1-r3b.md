===VERDICT START===
# VERDICT: ui-A1 round 3b — DeepSeek (checker)
**Status:** APPROVED
**Round:** 3b

## Summary

Fix commit `9b97fa1` resolves the round-3 blocking finding. The WCAG AA contrast test now
derives `--surface`, `--text-muted`, and `--warning` from the shipped stylesheet
(`readFileSync` + `parseCssVar`, `frontend/src/layout/layout.test.tsx:5-9,568-576`) instead of
hardcoded literals, and the two self-fulfilling `it('mutation: …')` cases were deleted. Every
mutation below was run in a fresh `git archive HEAD | tar -x -C /tmp/qp1-ui-a1r3b-check` copy
with symlinked `frontend/node_modules`, via WSL node v22.23.3. Worktree left clean.

## 1. Contrast mutation now FAILS (round-3 finding closed)

`sed --text-muted→#94a3b8` + `--warning→#d97706` in `frontend/src/index.css:12,15`:

```
FAIL  layout.test.tsx > WCAG AA contrast tokens > --text-muted meets 4.5:1 on --surface
AssertionError: expected 2.5640413904962034 to be greater than or equal to 4.5
FAIL  layout.test.tsx > WCAG AA contrast tokens > --warning text meets 4.5:1 on --surface
AssertionError: expected 3.1858232404059073 to be greater than or equal to 4.5
Tests  2 failed | 75 passed (77)
```

The test reads the mutated token values from disk, so a stylesheet regression now fails exactly
the two named contrast tests. Vacuous hardcoded-literal assertions are gone.

## 2. Dark-mode token mutations — not applicable (no dark block exists)

`frontend/src/index.css` defines tokens only under `:root` (lines 5-28). There is no
`@media (prefers-color-scheme: dark)`, no `.dark { }` block, and no dark-mode `--surface` /
`--text-muted` / `--warning` overrides anywhere under `frontend/src`. The many `dark:…` strings
in `Card.tsx`, `Table.tsx`, `FreshnessBadge.tsx`, etc. are Tailwind utility classes, not token
definitions. There is therefore no dark-mode token to mutate; the contrast test correctly covers
the single token block that actually ships.

## 3. A1 r3 mutations — none survive

- **Initial focus** — remove `wasOpen.current &&` guard at `MobileNavigation.tsx:39` → 1 fail
  (`does not steal focus on initial render when drawer is closed`).
- **`aria-modal` / trap** — delete `aria-modal="true"` at `MobileNavigation.tsx:84` → 1 fail
  (`drawer has aria-modal="true"`).
- **Collapsed accessible names** — delete `aria-label={collapsed ? item.label : undefined}` at
  `Sidebar.tsx:50` → 1 fail (`preserves full accessible name on collapsed nav buttons via aria-label`).
- **`min-w-[400px]`** — add to shell root `AppShell.tsx:51` → 1 fail (`expected 400 to be <= 360`,
  `enforces layout contract at 360px viewport width`).
- **Remove "Options Analytics"** — delete `App.tsx:38` → 2 fail (`renders every destination label…`
  and `navigates to each destination on click…`).

## 4. A2 mutations — none survive

- **N1 unversion keys** — strip `_v1` from `tourSteps.ts:3-5` → 4 fail (3× `writes qp_tour_*_v1 on
  close` + `stored _v1 key prevents auto-start (hardcoded key check)`).
- **N2 remove completion write** — drop `markTourSeen(tour.key)` at `TourHost.tsx:35` → 3 fail
  (`writes qp_tour_*_v1 on close`).
- **N3 missing selector blocks Next** — early-return in `CoachMarks.tsx:95` → 1 fail
  (`continues to next step when current selector is missing`).
- **N4 remove focus restore** — drop `openerRef.current?.focus()` at `CoachMarks.tsx:91` → 2 fail
  (`closes on Escape/Done and restores focus to the opener`).
- **N5 ArrowLeft wraps** — `back` wraps to last step `CoachMarks.tsx:102` → 1 fail
  (`ArrowLeft does not wrap to last step`).
- **N6 remove reduced-motion guard** — drop `if (prefersReducedMotion) return;` at `TourHost.tsx:54`
  → 1 fail (`does not auto-start under prefers-reduced-motion`).
- **N7 measure once** — drop resize/scroll listeners at `CoachMarks.tsx:76-77` → 2 fail
  (`repositions the spotlight after resize` / `after scroll`).

## 5. 79 → 77 test drop is only the two vacuous literal cases

`git log 4740459..HEAD -- '*test.tsx' '*test.ts'` returns only `9b97fa1`. Its diff removes
exactly two `it('mutation: changing --text-muted/-warning …')` blocks from
`layout.test.tsx` and adds no tests. `it(` count in `layout.test.tsx` drops 22 → 20; whole-suite
`it(` count is 77; `grep -r 'mutation:' frontend/src` = 0 matches. No other test was removed.

## Checks run

- `npx vitest --run` (baseline, clean copy) → **77/77 pass** (6 files).
- Contrast mutation (`--text-muted→#94a3b8`, `--warning→#d97706`) → **2 fail / 75 pass**.
- A1 mutations (initial focus, aria-modal, collapsed names, min-w-[400px], remove Options
  Analytics) → **1/1/1/1/2 fail** respectively.
- A2 mutations N1..N7 → **4/3/1/2/1/1/2 fail** respectively.
- `npx tsc --noEmit` → **pass** (exit 0).
- `npm run build` → **pass** (186.55 kB JS / 21.30 kB CSS).
- `git status --short` (repo) → clean.

## Non-blocking notes

- `readFileSync` runs at module load (`layout.test.tsx:9`), reading `index.css` from disk rather
  than through the Vite pipeline. This is fine for the token-parsing purpose but couples the test
  to the physical file path `../index.css`; renaming the CSS file would surface as a test error
  (acceptable, arguably desirable).
- The token regex in `parseCssVar` matches a 6-digit hex only; tokens using `rgb()`/`hsl()` or
  3/8-digit hex would throw. The shipped stylesheet uses only 6-digit hex, so this is not a defect.
- Contrast coverage is light-mode only because that is the only token block that ships; if a
  dark-mode block is ever added, the test will need a corresponding dark `--surface`/`--text-muted`
  /`--warning` pair (already flagged by BUILD-ui-A1-r3.md item 5 "and dark-mode equivalents").
===VERDICT END===
