===VERDICT START===
# VERDICT: sec-explorer (round 3) — DeepSeek
**Status:** APPROVED
**Round:** 3

## Blocking findings

None. All three mutations that survived round 2 are now killed, and the
three mutations that were already caught remain caught. Commit `b2d1438`
resolves every round-2 blocker.

## Verification (mutation copies in `/tmp/sec-r3-check` via `git archive HEAD`)

| Named mutation (spec) | Site | Result |
| :--- | :--- | :--- |
| no-coverage treated as empty (`isNoCoverage = false`) | `frontend/src/screens/SecFilingExplorer.tsx:134` | **1 fail** — `shows no-coverage message for ticker without processed filings` |
| tool_calls[0] used (`.find` → `[0]`) | `frontend/src/screens/SecFilingExplorer.tsx:129` | **1 fail** — `renders rows from search_sec_filings even when it is not the first tool call` |
| endpoint includes n_chunks=0 tickers (remove `WHERE n_chunks > 0`) | `api/routes/sec.py:44` | **1 fail** — `test_read_coverage_rows_excludes_nchunks_zero_via_sql` |
| initial state shows the empty message | `frontend/src/screens/SecFilingExplorer.tsx:264` | **1 fail** — `shows initial state before any selection` |
| selector caps the list (`slice(0, 16)`) | `frontend/src/screens/SecFilingExplorer.tsx:227` | **1 fail** — `selector caps the list (mutation: endpoint returns many items)` |
| fallback removed (`useFallback = false`) | `frontend/src/screens/SecFilingExplorer.tsx:138` | **3 fail** — `coverage failure…`, `coverage unavailable…`, `fallback free-text…` |

Each mutation was applied in the archive copy, the suite run, and the source
restored; the failing test names above were captured from the vitest/pytest
output (not inferred).

## Non-blocking notes

- The new backend test (`tests/api/test_sec_coverage.py:160-188`) catches the
  mutation by asserting the generated SQL string contains `n_chunks` and a
  `>`/`WHERE` predicate, rather than by executing the SQL. This is indirect
  (a reworded-but-still-filtering query could in principle evade it), but it
  does deterministically kill the specific `WHERE n_chunks > 0` removal and is
  acceptable for this contract.
- The new frontend tests use the real agent result shapes: `{error:
  'no_coverage', ticker}` (`agent/tools_retrieval.py:181`) and a
  `search_sec_filings` call placed after an unrelated `some_other_tool` call,
  matching the round-1 spec wording exactly.
- SQL safety still holds: `api/routes/sec.py:19-47` uses a constant table name
  with no user input; missing table / ImportError → 200 + `status:
  "unavailable"` (never 500), unchanged from round 2.

## Checks run

- `npx vitest --run` (full frontend) → **16 passed** (3 files)
- `python3 -m pytest tests/api -q` → **325 passed**
- `python3 -m pytest tests/api/test_sec_coverage.py -q` → **8 passed**
- `npx tsc --noEmit` → **clean** (exit 0)
- 6/6 named mutations → **each fails ≥1 test** (see table)

Round-2 blockers resolved; gate is met.
===VERDICT END===
