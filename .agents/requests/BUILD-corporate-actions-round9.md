# BUILD corporate-actions round 9 (builder: MiMo) — 3 wiring fixes from Codex

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/corporate-actions. Commit after each item, descriptive messages. LF endings.
NEVER delete or weaken existing tests. Codex review: .agents/codex/VERDICT-corporate-actions-review2.md (3 blocking; adjustment math verified).

1. resources/jobs.yml:27 passes `source: "yfinance"` (notebook accepts only massive → ValueError). Set `source: "massive"`; fix every command in
   docs/CORPORATE_ACTIONS_RUNBOOK.md (:44, :59, :66, :78 and any other) to Massive. grep the repo for remaining `yfinance` in corporate-actions
   wiring/docs. Test: parse resources/jobs.yml and assert every corporate-actions task's source is in the notebook's VALID_SOURCES; a test that
   extracts runbook commands' --source values and asserts they're valid.
2. Checkpoint SUCCESS only after the bronze append AND a post-append key check (notebooks/refresh_bronze_corporate_actions.py:417 vs :438).
   Restructure: fetch → append batch → verify the batch's (symbol, ex_date, source) keys exist → then mark SUCCESS for those symbols.
   Test: simulate a crash between fetch and append (raise in the writer) → on resume with the same run_id the symbol is NOT skipped and its rows
   get written. Mutation: mark SUCCESS before append → FAILS.
3. Rate limit on empty responses: the no-split `continue` (:397) skips the only per-symbol sleep (:430); the adapter stores `_delay`
   (etl/corporate_actions.py:143) but never uses it. Enforce the minimum inter-request delay INSIDE the adapter (before each HTTP request,
   including pagination pages), not in the notebook loop. Test with a fake clock/sleep: N symbols with empty results → N−1 sleeps of ≥ delay
   (or monotonic spacing ≥ delay). Mutation: remove the adapter delay → FAILS.
Acceptance: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py all pass; pyspark hidden
(PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps). .agents/mimo/VERDICT-corporate-actions-round9.md
with counts + mutation outputs. Commit everything.
