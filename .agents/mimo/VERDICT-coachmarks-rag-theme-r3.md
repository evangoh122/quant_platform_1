# VERDICT: coachmarks-rag-theme-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
- None.

## Non-blocking notes
- The `inert` attribute uses a spread `{...{ inert: '' }}` to bypass React 18 types (inert is not in `@types/react@18.3.12`). Works at runtime and in Vite build.
- `window.location.hash` is always empty in jsdom, so tour screen restore uses a `currentScreen` prop instead.

## Checks run
- `npx tsc --noEmit` → pass (0 errors)
- `npx vite build` → pass (1.93s, 68 modules)
- `npx vitest run` → pass (315/315 tests, 16 files, 8.49s)

## Mutation proofs
- F1: Test 1 fails if `AppShell.tsx:42-45` hardcodes `tour: 'application'` (real AppShell rendered)
- F2: Test 8 fails if manual replay checks `tourSeen()` (seeds real production keys)
- F3: Test 5 fails if CSS removes `min-height: 44px` / `min-width: 44px` in `@media (max-width: 767px)`
- F4: App tests fail if `_v1` keys used instead of current versioned constants
- B1: Test 10 fails if `bg-blue-*` restored in ToolCallCard
