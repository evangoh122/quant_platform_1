# VERDICT: ui-A1 round 3b — MiMo
**Status:** APPROVED
**Round:** 3b

## Blocking findings
None.

## Non-blocking notes
- `import css from '../index.css?raw'` returns an empty string in vitest 2.1.9 (Vite CSS pipeline intercepts `?raw` queries for `.css` files). Used `fs.readFileSync` with `node:fs`/`node:path`/`node:url` imports instead. Added `@types/node` to devDependencies to satisfy TypeScript.
- Removed both vacuous "mutation" test cases that asserted hardcoded low-contrast literals (`#94a3b8`, `#d97706`) against the hardcoded `SURFACE = '#ffffff'` — these were self-fulfilling and tested nothing in the shipped stylesheet.

## What was done
1. **layout.test.tsx** — Replaced hardcoded `SURFACE`, `TEXT_MUTED`, `WARNING` constants with values parsed from `frontend/src/index.css` at test time via `readFileSync` + `parseCssVar()` regex.
2. **layout.test.tsx** — Deleted the two `mutation: ...` test cases (lines 576-582 of the original file).
3. **package.json** — Added `@types/node` to devDependencies for TypeScript `node:*` module support.

## Mutation verification (clean copy)
Built with `git archive HEAD | tar -x -C /tmp/qp1-ui-r3b-check` + symlinked `node_modules`.

Baseline (HEAD `9b97fa1`):
- `npx vitest --run` → **77/77 pass**

Mutation: `--text-muted→#94a3b8`, `--warning→#d97706` in `index.css`:
- `--text-muted meets 4.5:1 on --surface` → **FAILED** (2.56:1 < 4.5)
- `--warning text meets 4.5:1 on --surface` → **FAILED** (3.19:1 < 4.5)
- **2 failed / 75 pass** — contrast regression correctly caught.

## Checks run
- `npx vitest --run` (baseline) → **77/77 pass**
- `npx tsc --noEmit` → **pass** (exit 0)
- `npm run build` → **pass** (186.55 kB JS / 21.30 kB CSS)
- Mutation test (clean copy, `--text-muted→#94a3b8`, `--warning→#d97706`) → **2 failed / 75 pass**

## Commit
`9b97fa1` on `feat/ui-enhancement`