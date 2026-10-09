# VERDICT: decision-p0a-r2 — DeepSeek
**Status:** APPROVED
**Round:** 2

## Blocking findings
(none)

## Non-blocking notes
- `market_features_intraday` (db/delta_adapter.py:475) is **left unordered**, and I judge this **acceptable, not a blocker**. The r2 mandate conditions the fix on "the matching warehouse query is newest-first", but `_build_market_features_intraday_query` (db/delta_adapter.py:85-94) has **no** `ORDER BY`. Both backends are nondeterministic today, so there is no backend row-order disagreement (the defect class B1 is about). It is a residual nondeterminism on *both* paths, not a regression. Recommend a follow-up that adds `ORDER BY feature_ts DESC` to the warehouse builder and the Spark branch *together* (and decides an explicit ordering contract for `read_table`, db/delta_adapter.py:401).
- `read_analytics_cdc_state` (db/delta_adapter.py:527) `.limit(1)` is arbitrary only if `analytics_cdc_state` ever holds >1 row; acceptable for a single-row state table.
- `read_analytics_table` Spark branch now orders `event_date DESC`, but the order clause is assumed valid for all 7 sections (a section whose table lacks `event_date` would now raise → caught → `[]`, same as the pre-existing warehouse fallback `ORDER BY event_date DESC`). Pre-existing warehouse behaviour, not a regression; no action required this round.

## Checks run
- `git rev-parse HEAD` → `eb1c931f5dffba8e3b5211d3569c2049f5883797` (matches request) → pass
- `git status --porcelain --untracked-files=no` → clean → pass
- `git merge-base --is-ancestor origin/main HEAD` → pass (merge-base `45f6979` = origin/main)
- Scope audit (`git diff --name-only origin/main...HEAD`): r2 (`aacee9c...HEAD`) touches only `.agents/*` evidence/request/harness, `agent/tools_retrieval.py`, `api/trading_days.py` (docstring only), `db/delta_adapter.py`, and test files; no `requirements*`/`package.json`/lock changes; no new deps; no new `api/routes/` changes beyond Phase 0a → pass
- Secret scan (`git diff origin/main...HEAD | grep -Ei 'password|secret|token|PRIVATE|AKIA|DATABRICKS_TOKEN'`) → none → pass
- **B1 re-verified resolved:** `db/delta_adapter.py:457` market_features PySpark now `.orderBy(F.col("event_date").desc()).limit(limit)`, matching `_build_market_features_daily_query` (`ORDER BY event_date DESC`, line 69) → pass
- **COT warehouse ORDER BY correct:** `_build_cot_query` adds `ORDER BY report_date DESC` only; `report_date` ∈ `_COT_COLS` (agent/tools_retrieval.py:38), column set unchanged, `get_cot_positioning` returns `rows[0]` = newest report on both backends → pass
- Site audit reproduced: `market_features` CHANGED, `read_analytics_table` CHANGED (warehouse `ORDER BY event_date DESC` confirmed pre-existing at aacee9c), `get_cot_positioning` + `_build_cot_query` CHANGED, `read_table`/`market_features_intraday`/`read_analytics_cdc_state` LEFT with valid reasons per mandate → pass
- Tests call real production functions with recording Spark stub (`_has_pyspark=True`, stubbed `_spark()`); no copied production logic (reviewed `tests/agent/test_delta_adapter_ordering.py`, `tests/agent/test_tools_retrieval_ordering.py`) → pass
- `.agents/run-mutations.py` no longer uses `--noconftest` (grep `noconftest` → none); M4 kills via semantic NULL assertion → pass
- `api/trading_days.py` docstring: verified accurate (`start_for_trading_days(Wed, 5)` = preceding Wednesday; weekend roll-back without count) → pass
- `.agents/run-decision-p0a-check.sh` via `wsl.exe -d Ubuntu -- bash ...` → `490 passed in 65.86s`; vitest `16 passed / 246 tests`; `npx tsc --noEmit`; `npm run build` ✓ → pass
- Independent mutation re-run `python3 .agents/run-mutations.py` (isolated `git archive eb1c931` copies, conftest loaded) → M1-M7 all PASS with the expected kill signatures (M4 via `expected NULL`, not a parser error) → pass

VALIDATION DONE | verdict: APPROVED | sha: eb1c931f5dffba8e3b5211d3569c2049f5883797 | evidence: .agents/deepseek/VERDICT-decision-p0a-r2.md
