===VERDICT START===
# VERDICT: app-resilience-round12 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 12 (check)
**Range:** 7c5128a (fix source labels), dd10994 (smoke mocks), bd150e5 (Vitest frontend tests) on `slice/app-frontend-deploy`; re-review of Codex survivors in `.agents/codex/VERDICT-app-frontend-deploy-2.md`.

All four Codex survivors are now fixed and load-bearing. Re-ran every mutation from the request in archive/copy copies; each now fails. Full suite and frontend build/tests pass; nothing from the r11b PASS list regressed.

## Blocking findings

None.

## Fixes verified (previously Codex survivors, now killed)

1. **Source-label regression — FIXED.** `api/routes/market.py:64`, `:86`, `:87` now
   report `silver_ohlcv_day_adjusted` (was `gold_ohlcv_features`), and the dashboard
   empty-state at `frontend/src/screens/MarketDashboard.tsx:85` names the same table.
   New guard `tests/api/test_market.py:141-153` (`test_ohlcv_source_label_is_silver`)
   asserts `ohlcv.source` and `ohlcv.freshness.table` == `silver_ohlcv_day_adjusted`.
   Mutation (archive copy `sed s/silver_ohlcv_day_adjusted/gold_ohlcv_features/g`) →
   **1 failed** (`test_ohlcv_source_label_is_silver: AssertionError`). Killed.

2. **Smoke frontend-check bypass — FIXED.** `tests/test_smoke_app.py:93-105` and
   `:120-132` now mock every API endpoint (`/api/health`, `/api/signals`,
   `/api/market/NVDA`, `/api/analytics`, `/api/portfolio`, `/api/watchlists`) so the
   `GET /` frontend check is the *sole* failing condition, and each asserts
   `"FAIL  GET /"` in captured stdout. Mutation (`scripts/smoke_app.py:53`
   `_check_frontend_build` → `return True`) → **2 failed** (`test_smoke_fails_on_json_hint`,
   `test_smoke_fails_on_non_html`), 3 passed. Killed.

3. **Max-date reducer — FIXED.** `frontend/src/screens/MarketDashboard.tsx:32-35`
   keeps the `reduce` over `event_date`; new `frontend/src/screens/MarketDashboard.test.tsx`
   feeds unsorted rows and asserts `160.00` (the `2025-01-15` close, not `data[0]`'s
   `2025-01-10`). Mutation (`const latest = data?.ohlcv.data[0]`) →
   **1 failed** (`MarketDashboard.test.tsx:41`), 2 passed. Killed.

4. **Lakebase health banner — FIXED.** `frontend/src/App.tsx:52-54` computes
   `lakebaseDown` from `dependencies` (`!d.ok || circuit_breaker_state === 'open'`);
   new `frontend/src/App.test.tsx` renders degraded vs healthy health payloads and
   asserts the banner at `App.tsx:81` appears/disappears. Mutation
   (`const lakebaseDown = false`) → **1 failed** (`App.test.tsx:55`), 2 passed. Killed.

## Dependency hygiene

- `frontend/package.json` adds only: `test` script + `@testing-library/jest-dom`,
  `@testing-library/react`, `jsdom`, `vitest` (devDependencies). `vite` entry only
  gained a trailing comma (version unchanged). No `dependencies` (react/react-dom) touched.
- `frontend/package-lock.json` changes are purely additive (Vitest/testing-library/jsdom
  + transitive deps) with no existing package version change: the only non-additive line
  is `autoprefixer`, whose entry is byte-identical to the parent commit
  (`10.6.1` in both `bd150e5^` and HEAD) — a harmless reorder on lock regeneration.
- `npm ci` → `added 222 packages`; `npm run build` → `48 modules transformed`,
  `dist/index.html` + hashed assets produced.

## r11b regression check

- Full suite now **1551 passed** (r11b: 1550) — the +1 is the new
  `test_ohlcv_source_label_is_silver`; 0 failures. r11b focused items re-run green:
  `test_token_mint_subprocess_timeout`, `test_warehouse_query_semaphore_bounded` (8 passed
  in the targeted batch including smoke + label tests).

## Checks run

- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` (WSL)
  → **1551 passed, 97 skipped, 24 deselected, 44 warnings** in 210.94 s (0 failed).
- `cd frontend && npm ci && npx vitest --run && npm run build` (Windows-path copy of
  `frontend/` to bypass the WSL UNC limitation) → npm ci `added 222 packages`;
  `npx vitest --run` → **3 passed (2 files)**; `npm run build` → `tsc && vite build`,
  `48 modules transformed`, `dist/` produced. All pass.
- Targeted batch: `pytest -q tests/api/test_resilience.py::test_token_mint_subprocess_timeout
  tests/api/test_health_diagnostics.py::test_warehouse_query_semaphore_bounded
  tests/api/test_market.py::test_ohlcv_source_label_is_silver tests/test_smoke_app.py`
  → **8 passed** in 1.94 s.
- Mutation A (max-date → `data[0]`) → `npx vitest --run` **1 failed**.
- Mutation B (banner → `false`) → `npx vitest --run` **1 failed**.
- Mutation C (`_check_frontend_build` → `return True`) → `pytest tests/test_smoke_app.py` **2 failed**.
- Mutation D (label revert) → `pytest tests/api/test_market.py::test_ohlcv_source_label_is_silver` **1 failed**.
- `git status` → working tree clean (no repo files edited).

## Non-blocking notes

- `npm ci` reports 10 vulnerabilities (3 moderate, 6 high, 1 critical) in the
  transitive dev tree — pre-existing and out of scope for this slice; the build/test
  suite does not consume those paths.
- Windows `node` cannot run `npm`/`vitest` through the WSL UNC path
  (`\\wsl.localhost\…`); frontend verification was performed on a local Windows-path
  copy, consistent with prior rounds. Not a code defect.
- `git status` via the Windows UNC view shows `.agents/dispatch.sh` "modified" (a
  line-ending artifact), while WSL git reports a clean tree; pre-existing, not
  introduced by this check.
===VERDICT END===
