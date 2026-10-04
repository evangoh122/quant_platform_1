# BUILD-rag-coverage round 11 — IMPLEMENT NOW (Codex sol CHANGES_REQUESTED)

You are MiMo. Fix the single P1 from `.agents/codex/VERDICT-rag-coverage-r3.md` on this branch.

## Finding to fix
Missing MERGE metrics are still silently reported as zero.
- `pipelines/sec_rag_ingest.py:~1709` and `pipelines/build_sec_embeddings.py:~278` initialise the
  inserted count to `0`. If `DESCRIBE HISTORY` returns no row, or `operationMetrics` lacks
  `numTargetRowsInserted`, they return `0` with no warning.
- `pipelines/build_sec_embeddings.py:~155` converts a batch-level `None` into `0`, so even the
  exception path reports a known-zero `rows_written`.

## Required behaviour
1. Missing history row, missing metrics key/map, and exceptions all return `None` and log a `WARNING`.
2. Unknown (`None`) propagates through the build-level aggregate: if any batch is unknown, the total
   `rows_written` is `None` (not a partial sum, not 0). The rollout idempotency gate must treat `None`
   as "not proven zero".
3. A real reported `0` stays `0`.

## Tests (behavioural, must fail on current HEAD — capture red phase)
- For both writers: empty history → None + WARNING; metrics map without key → None + WARNING;
  exception → None + WARNING; metrics with "0" → 0; metrics with "7" → 7.
- Aggregate: [3, None, 2] → None; [0, 0] → 0.
- Mutations that must fail: re-initialise count to 0; `or 0` coercion in aggregate.

Rules: commit per item, LF endings, do not touch `.agents/dispatch.sh`, mutation copies via
`git archive HEAD | tar -x -C /tmp/<dir>`. Run `python3 -m pytest tests/rag tests/bronze -q`.
Verdict to `.agents/mimo/VERDICT-rag-coverage-round11.md`.
