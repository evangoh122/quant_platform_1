# VERDICT: viz-V5 — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None

## Non-blocking notes
- The `db/delta_adapter.py` `read_sql` function was extended to accept an optional `params` dict for parameterized queries. Previously it only accepted a raw SQL string. This is a non-breaking additive change.
- The `tests/api/test_public_demo_security.py` was updated to add `?asset_class=equity_index` to the positioning route test iteration, since the route requires this query parameter.
- Asset manager percentile stat tile displays the raw value from the API (e.g., 74%) rather than multiplying by 100 again. The API returns values like 72, 74 (already in percent form).

## Checks run
- `python -m pytest tests/api/test_positioning.py -v` → 9 passed
- `python -m pytest tests/api/ -q` → 336 passed
- `npx vitest run src/screens/Positioning.test.tsx` → 7 passed
- `npx tsc --noEmit` → pass (no type errors)
- `npx vite build` → pass (built in 3.25s)
- Mutation: remove release_ts filter → `test_release_ts_filter_excludes_future_rows` FAILED (correctly detects removal)
- Mutation: add OI concentration line → `options card shows OI concentration as stat, no OI line` FAILED (correctly detects the chart)

## Files created/modified
- `api/schemas.py` — added CotWeeklyRow, CotContractRow, PositioningResponse
- `api/routes/positioning.py` — new route GET /api/positioning/cot
- `api/main.py` — registered positioning router
- `db/delta_adapter.py` — added params parameter to read_sql
- `frontend/src/api/types.ts` — added CotWeeklyRow, CotContractRow, PositioningResponse
- `frontend/src/api/client.ts` — added positioning() method
- `frontend/src/screens/Positioning.tsx` — new screen with asset-class selector, net positions chart, percentile band, contract diverging bars, options card
- `frontend/src/App.tsx` — added positioning nav entry
- `tests/api/test_positioning.py` — 9 API tests
- `frontend/src/screens/Positioning.test.tsx` — 7 frontend tests
- `tests/api/test_public_demo_security.py` — fixed route iteration for positioning