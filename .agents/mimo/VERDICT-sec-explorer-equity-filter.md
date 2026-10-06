# VERDICT: sec-explorer-equity-filter — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
- None

## Non-blocking notes
- The `_read_coverage_rows` function imports `_fqn` and `_warehouse_query` from `db.delta_adapter` (private functions). This is consistent with how the module is used elsewhere in the codebase, but could be refactored to use a public API in the future.
- The frontend selector renders all 228 items in the dropdown without virtualization. At 228 items this is fine, but if the list grows significantly, consider virtualizing.

## Checks run
- `python3 -m pytest tests/api/test_sec_coverage.py -v` → 7/7 passed
- `python3 -m pytest tests/api -q` → 324 passed (no regressions)
- `npx vitest --run src/screens/SecFilingExplorer.test.tsx` → 11/11 passed
- `npx tsc --noEmit` → pass (no type errors)
- `npm run build` → pass (built in 1.85s)

## Implementation summary

### Backend (`api/routes/sec.py`)
- `GET /api/sec/coverage` returns `{data, count, status}` where status is `"ok"` or `"unavailable"`
- Reads `gold_sec_coverage` via `delta_adapter._warehouse_query` with `WHERE n_chunks > 0 ORDER BY ticker`
- Constant table name, no user input in SQL (parameterized)
- Pydantic response model `SecCoverageResponse` with `SecCoverageItem`
- Table missing / ImportError → 200 with empty list + `"unavailable"` status
- Registered in `api/main.py` at `/api/sec` prefix

### Frontend (`SecFilingExplorer.tsx`)
- Fetches `/api/sec/coverage` on mount
- Shows "N equities with SEC filings" count above selector
- Searchable combobox: type-ahead filter by ticker, shows filing count + last filed date
- Keyboard accessible: ArrowUp/Down to navigate, Enter to select, Escape to close
- Works at 360px (responsive max-width)
- Coverage failure → falls back to free-text input with amber notice banner
- Keeps round-1 states: initial / loading / no-coverage / empty / error

### Tests
- Backend: 7 tests covering sorted output, n_chunks=0 exclusion, missing table, ImportError, empty result, field mapping, mutation check
- Frontend: 11 tests covering loading state, equity count, ticker list, filtering, selection triggers chat, coverage failure fallback, unavailable status fallback, fallback still works, filing count display, 228-item list, initial state