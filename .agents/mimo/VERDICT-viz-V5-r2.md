# VERDICT: viz-V5-r2 — MiMo
**Status:** APPROVED
**Round:** 2

## Blocking findings
None.

## Non-blocking notes
- The `?? 0` mutation test for the frontend is indirect: the existing stacked-bars test (`callH ≈ putH * 3`) catches it when both volumes are present, and the null-call test catches the missing-rect case. The `?? 0` operator is only evaluated when `call_volume != null`, so a separate mutation that removes the `if (r.call_volume == null) return null` guard would also be needed to fully exercise the path. This is adequate for round 2 but could be tightened in a future round.

## Checks run
- `python -m pytest -q --timeout 120 tests/api/test_positioning.py` → 11 passed
- `npx vitest run frontend/src/screens/OptionsAnalytics.test.tsx` → 9 passed
- `npx tsc --noEmit` → 0 errors
- `npx vite build` → built in 1.99s

## Changes made

### Fix 1: Weekly COT query — `information_available_ts <= :now` (positioning.py:75-76)
Added `AND information_available_ts <= :now` predicate to the `_read_weekly` SQL query. Passes `now_str` parameter. Mutation test: dropping the predicate fails `test_weekly_query_excludes_future_information_available`.

### Fix 2: Contracts — latest released week only (positioning.py:96-102)
Added `AND report_date = (SELECT MAX(report_date) FROM silver_cot_positions WHERE mapped_asset = :asset_class AND release_ts <= :now)` subquery to the `_read_contracts` SQL. Mutation test: dropping the subquery fails `test_contracts_only_latest_released_week`.

### Fix 3: Null volume incomplete style (OptionsAnalytics.tsx:113-152, BarSeries.tsx:1-8,18-30)
- `putBars`: when `put_volume != null` but `call_volume == null`, renders with dashed green stroke (`stroke: '#22c55e', strokeDasharray: '4,2'`) and "call missing" label.
- `callBars`: when `call_volume != null` but `put_volume == null`, renders from baseline with dashed red stroke (`stroke: '#ef4444', strokeDasharray: '4,2'`) and "put missing" label. Both null → no bar.
- `BarSeries`: extended `BarDatum` interface with optional `stroke` and `strokeDasharray` props, passed through to `<rect>`.
- Tooltip: appends " · put missing" / " · call missing" / " · data incomplete" when volumes are null.
- Table columns and `tableData`: show "— (put missing)" / "— (call missing)" for null volumes.
- Mutation test: `test_draws_a_missing_segment_when_call_volume_is_null` (no rect in call group) and `test_call_bar_stacks_on_top_of_put_bar` (stacking height ratio) catch the `?? 0` regression.

### Test additions (test_positioning.py, OptionsAnalytics.test.tsx)
- `test_weekly_query_excludes_future_information_available` — captures SQL, asserts `<= :now` predicate and `:now` param.
- `test_contracts_only_latest_released_week` — captures SQL, asserts `MAX(report_date)` subquery.
- `test_draws_a_missing_segment_when_put_volume_is_null` — existing, unchanged.
- `test_draws_a_missing_segment_when_call_volume_is_null` — new, verifies no rect in call group when call_volume is null.
- `test_call_bar_stacks_on_top_of_put_bar` — new, verifies call bar height is 3× put bar height (100/300 split), catches `?? 0` mutation.