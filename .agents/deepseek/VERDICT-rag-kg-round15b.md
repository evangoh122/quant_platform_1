===VERDICT START===
# VERDICT: rag-kg-round15b — DeepSeek (checker)
**Status:** APPROVED
**Round:** 15b
**Range:** b31a539 (fix(kg): fake DataFrame records collect/toLocalIterator/count …) on slice/rag-kg

Re-check of my two round-15 blocking findings against Claude's fixes. Both are resolved.

## Blocking findings

None.

## Findings re-verified (previously blocking, now fixed)

1. **Vacuous mutation guard (round-15 finding #1) — FIXED.**
   `_FakeDataFrame` now records its data-path calls: `collect()` →
   `write_spy.record("collect")` (tests/rag/test_sec_knowledge_graph.py:2135),
   `toLocalIterator()` → `write_spy.record("toLocalIterator")` (:2138),
   `count()` → `write_spy.record("count")` (:2143). The assertion in
   `test_mutation_count_after_collect_fails` (tests/rag/test_sec_knowledge_graph.py:3727-3771)
   is now load-bearing. **Mutation proof (re-run)**: moving the cap check back
   AFTER the `toLocalIterator` loops (pipelines/build_sec_knowledge_graph.py:102-111
   relocated after the entities loop, archive copy at `/tmp/ds-mut1`) → the test
   FAILS with `assert 2 == 0` (spy records 2 `toLocalIterator` calls before the
   count fires). Mutation killed; the cap-before-collect ordering is genuinely tested.

2. **Trailing-newline metric/period (round-15 finding #2) — FIXED.**
   Metric now uses `re.fullmatch(r"[A-Za-z][A-Za-z0-9._:\-]*", v)`
   (agent/tools_retrieval.py:275) and period uses `_PERIOD_RE.fullmatch(v)`
   (agent/tools_retrieval.py:300). All three CHECK cases are rejected by the
   Pydantic validators **before** `graph.get_fact` is called:
   - `"Revenues\n"` → `ValueError` from `_valid_metric` (metric regex).
   - `"2023\n"`, `"2024-Q1\n"` → `ValueError` from `_valid_period` (period regex).
   The behavioural parametrized test `test_metric_and_period_reject_trailing_newline`
   (tests/rag/test_sec_knowledge_graph.py:5080-5085) covers exactly these three cases.

## Note on defense-in-depth (as requested in the CHECK)

With the period regex reverted to `.match` (archive copy `/tmp/ds-mut2`,
`fullmatch`→`match` only), `_valid_period` accepts `"2023\n"`/`"2024-Q1\n"`, yet
the period cases **still raise** — via a *partial* second layer, not the front-end
validator:

- `SecKnowledgeGraph.get_fact` (api/services/sec_knowledge_graph.py:626) calls
  `parse_period` (sec_kg/model.py:353), which runs `normalize_unicode` (strips the
  trailing newline) then `iso_date` (sec_kg/model.py:90). `iso_date` only accepts a
  strict `YYYY-MM-DD` (length 10, dashes at positions 4/7), so `"2023"` and
  `"2024-Q1"` raise `ValueError("Invalid date format: …")`. Empirically, in `/tmp/ds-mut2`:
  `"2023\n"` → `ValueError: Invalid date format: '2023'`; `"2024-Q1\n"` →
  `ValueError: Invalid date format: '2024-Q1'`.

This defense-in-depth is **partial**, not a substitute for the `fullmatch` fix:
- It does **not** catch a trailing newline on a valid date — `"2024-01-28\n"`
  passes `_valid_period` (under `.match`), `iso_date` strips and accepts it, and the
  call proceeds to the Spark backend (RuntimeError from Databricks Connect proves it
  reached the store). So the period `fullmatch` remains the primary guard.
- The metric side has **no** such second layer — reverting only the metric regex to
  `.match`+`$` (archive copy `/tmp/ds-mut3`) lets `"Revenues\n"` through `_valid_metric`
  all the way to the backend (RuntimeError, not a validation error). The metric
  `fullmatch` is therefore load-bearing and essential.

## Non-blocking notes

- Pre-existing format mismatch surfaced while tracing the above: `_valid_period`
  accepts `YYYY`, `YYYY-Qn`, and `YYYY-MM-DD..YYYY-MM-DD`, but the backend
  `parse_period`/`iso_date` only actually supports `YYYY-MM-DD` and
  `YYYY-MM-DD/YYYY-MM-DD` (slash, not `..`). Consequently `"2023"`, `"2024-Q1"`, and
  `"2024-01-28..2024-03-31"` pass the front-end validator yet fail downstream with
  `ValueError: Invalid date format`. Pre-existing (not introduced by this round);
  worth aligning in a later round, out of scope here.

## Checks run

- `python3 -m pytest tests/rag -q` → **478 passed, 19 skipped, 1 warning** (30.1s)
  (was 475 passed pre-fix; +3 from the new parametrized behavioural test).
- Mutation 1 (cap check after loops, `/tmp/ds-mut1`):
  `python3 -m pytest tests/rag/test_sec_knowledge_graph.py -q -k test_mutation_count_after_collect_fails`
  → **1 failed** (`assert 2 == 0`, 2 `toLocalIterator` calls recorded). Killed.
- Mutation 2 (period `fullmatch`→`match`, `/tmp/ds-mut2`):
  `python3 -m pytest tests/rag/test_sec_knowledge_graph.py -q -k trailing_newline`
  → **3 passed** (period cases still raise via backend `iso_date`); direct probe:
  `"2023\n"`/`"2024-Q1\n"` → `Invalid date format`; `"2024-01-28\n"` → reaches backend.
- Mutation 3 (metric `fullmatch`→`match`+`$`, `/tmp/ds-mut3`): direct probe
  `"Revenues\n"` → reaches Spark backend (no validation error). Metric guard is essential.
- `re.match(r"^\d{4}$|…", "2023\n")` / `re.match(r"\d{4}|…", "2023\n")` → True;
  `re.fullmatch` variants → False (trailing newline rejected only under fullmatch).
===VERDICT END===
