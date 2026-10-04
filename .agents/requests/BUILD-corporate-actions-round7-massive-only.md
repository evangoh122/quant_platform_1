# BUILD corporate-actions round 7 — MASSIVE ONLY (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Commit after each item with descriptive
messages. LF endings. NEVER weaken tests that still apply; tests that only exist for the yfinance dual-source logic may be removed
(list each removed test name + why in your verdict).

## Owner decision (2026-10-04)
"use massive only with data from the corporate actions table from massive — download that into bronze and then solve it in silver."
- Bronze: bronze_corporate_actions is populated from the Massive REST splits endpoint ONLY (source='massive').
- Silver: silver_ohlcv_day_adjusted applies ONLY source='massive' splits. No yfinance anywhere in the adjustment path.
- The previous round-7 request (BUILD-corporate-actions-round7.md, dual-source) is SUPERSEDED; do not implement it.
  The abandoned dual-source work is parked on branch wip/corpact-r7-dual-source — do not merge it.

## 1. Remove yfinance from the pipeline
- notebooks/refresh_bronze_corporate_actions.py: VALID_SOURCES = {"massive"}; drop `yfinance` and `both` modes, the yfinance adapter
  wiring and per-source resume complexity (checkpoint keyed by symbol is enough again, but keep it correct).
- etl/corporate_actions.py: remove YFinanceCorporateActionsSource (and the yfinance dependency from requirements if nothing else uses
  it — grep first). Keep the CorporateActionsSource protocol + MassiveCorporateActionsSource (pagination, bounded retry, 401/403,
  key redaction with `raise ... from None`, exact-ticker filter, ratio = split_to/split_from).
- Keep the key redaction at the notebook boundary.

## 2. Silver: Massive only, simple and correct
silver/08_silver_ohlcv_day_adjusted.sql:
- Replace `_resolved_splits` + `_split_source_mismatches` with a single `_massive_splits` CTE: `WHERE source = 'massive'`, deduped to one
  row per (symbol, ex_date) (latest fetched_ts wins — Massive can return the same split twice across runs).
- Remove SPLIT_SOURCE_MISMATCH / SPLIT_SINGLE_SOURCE (they no longer exist). Keep the existing price-jump data_quality_breaks logic
  (unexplained large moves, and a split whose same-day move doesn't match the ratio within tolerance) — that is the sanity check
  on Massive's data now. Explicit column lists in every INSERT/MERGE.
- Any rows in bronze_corporate_actions with another source must be IGNORED by silver (filter), not deleted.

## 3. Tests (real SQL, DuckDB, extracted from silver/08 at test time — no retyped SQL)
- AMZN 20:1 on 2022-06-06 → cumulative factor 20 for bars before, adj_close continuity ≈ +2% across the split (not −95%).
- Duplicate massive rows same (symbol, ex_date) → applied once (factor 20, not 400). Mutation: remove the dedupe → FAILS.
- SQQQ reverse 5:1 (ratio 0.2) → factor 0.2.
- A yfinance-source row present in bronze → ignored (factor unchanged). Mutation: drop the source filter → FAILS.
- Price-jump break: an unexplained −50% move with no split → one data_quality_breaks row; a split day whose move matches the ratio
  → no break row.
- Key-leak tests still pass (fake session errors containing apiKey=SECRET123 never surface).
- duckdb in requirements (dev/test) to match CI.

## 4. Docs
docs/DATA_SCHEMAS.md + notebook docstring: Massive-only source, dedupe rule, back-adjusted (split-only, not dividends) caveat.

## Acceptance
python -m pytest -q tests/bronze tests/silver tests/test_security.py — all pass except the 5 pre-existing
tests/bronze/test_refresh_bronze_cot.py::TestComputeReleaseTs failures (don't touch); pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps) same.
.agents/mimo/VERDICT-corporate-actions-round7.md with counts, removed-test list, and mutation outputs. Commit everything.
