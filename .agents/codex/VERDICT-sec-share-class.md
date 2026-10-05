# Codex gpt-5.6-sol review — share-class (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

api/services/hybrid_retriever.py:493-519 — SQL and API canonical selection disagree. `gold_sec_coverage` reports the resolved canonical `n_chunks` for every alias (`gold/07_gold_sec_coverage.sql:93-103`), so GOOG and GOOGL both contain `831`. `_load_alias_map()` therefore sees a tie and alphabetically selects GOOG, recreating the original bug. The API tests incorrectly supply pre-resolution counts (`GOOG=0`, `GOOGL=831`) rather than actual gold-table rows.

Required: persist/read the canonical ticker directly, or otherwise provide per-ticker raw chunk counts to the API. Add an integration-shaped test using `GOOG=831` and `GOOGL=831` as emitted by gold and prove both resolve to GOOGL.

Validation:
- Required suite: 269 passed, 2 skipped.
- `/tmp` mutation proof: reverting both implementations caused 4 targeted failures, as expected.
- Single-ticker CIK behavior remains correct.
- Unmapped BRK.A identity behavior is acceptable.
- SQL contains no user input.
===VERDICT END===
