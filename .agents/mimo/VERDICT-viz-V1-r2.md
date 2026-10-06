# VERDICT: viz-V1-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none)

## Non-blocking notes
- Bar width increased from 0.35 to 0.5 of xStep for single-bar-per-row layout; visual density is improved.
- `null` put or call correctly renders as a missing segment (no rect emitted) rather than a zero-height bar pretending to be data.

## Changes made
- `frontend/src/screens/OptionsAnalytics.tsx:109-135` — Stacked put/call bars: both bars now share the same x (centered via `barX`), put starts from chart bottom, call starts from top of put segment. Null values produce no rect element.
- `frontend/src/screens/OptionsAnalytics.tsx:183-184` — BarSeries arrays filtered to exclude nulls before passing to component.
- `frontend/src/screens/OptionsAnalytics.test.tsx` — Added two tests:
  - `renders put/call bars as stacked (not side-by-side)`: verifies call y+height equals put y, same x, same width, and callH ≈ 3× putH for put=100/call=300.
  - `draws a missing segment (not zero) when put_volume is null`: verifies no put rect and a call rect still renders.

## Checks run
- `npx vitest run` → 197/197 passed (18 files)
- `npx tsc --noEmit` → pass (0 errors)
- `npx vite build` → pass (76 modules, 3.97s)