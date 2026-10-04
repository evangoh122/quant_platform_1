# VERDICT: rag-kg-round10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings
None.

## Non-blocking notes
- `propose_xbrl_qa_candidates` in `sec_kg/build.py` still uses `iter_nodes()` (full scan). Not in scope for this round.
- `find_nodes` uses `properties_json.contains()` for Spark-side filtering, which is a substring match. This works correctly with `deterministic_json`'s compact format (`separators=(",",":")`).

## Checks run
- `python3 -m pytest tests/rag -q` → **427 passed, 19 skipped, 0 failed**, 1 warning
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/rag -q` → **427 passed, 19 skipped, 0 failed**, 1 warning
- `git diff HEAD~1 --stat` → 4 files, +829/-30
- `git log --oneline -3` → HEAD `c738f1d` on `slice/rag-kg`

## Implementation summary

### 1. Query predicate pushdown
- `SparkGraphStore.find_nodes()` — pushes `node_type`, `ticker`, `concept` (both `entity_key` and `metric` keys), `period_start`, `period_end` into Spark `.where()` using column expressions. Hard `.limit(n)` applied BEFORE `.toLocalIterator()`.
- `SparkGraphStore.find_edges_by_node_ids()` — bounded `.isin()` on `src_id`/`dst_id` with optional `edge_types` and `as_of` filters. Hard `.limit(n)` before collect.
- `JsonlGraphStore.find_nodes()` / `find_edges_by_node_ids()` — same interface, in-memory filtering for test parity.
- `get_fact`, `facts_timeseries`, `risk_factors` now call `find_nodes()` instead of `iter_nodes()`.

### 2. Real TZ regression test
- `TestTimezoneRegression::test_singapore_tz_affects_naive_timestamp` — sets `TZ=Asia/Singapore` via `monkeypatch.setenv`, calls `time.tzset()`, asserts naive `.timestamp()` gives epoch 1700000000 for `2023-11-15T06:13:20` (UTC+8). Mutation proof: naive `datetime(2023,11,14,22,13,20).timestamp()` in Singapore gives wrong epoch. Skips on Windows (no `time.tzset`).

### 3. Full-rebuild delete safety
- `build()` now accepts `subset_filter` parameter (default `None`).
- When `subset_filter` is set, raises `ValueError` before `whenNotMatchedBySourceDelete` to prevent unscoped deletion.
- Logs existing row counts before merge for audit trail.
- Test: `TestSubsetFilterDeleteSafety::test_subset_filter_raises` verifies the guard.
- Test: `TestSubsetFilterDeleteSafety::test_no_subset_filter_succeeds` verifies normal path.

### 4. Docstring fix
- Removed inaccurate "274.3 million ↔ 274300000" scale-word matching claim from `_chunk_text_matches_value` docstring.

## Mutation proofs

### Mutation 1: predicate pushdown
- **Mutated** `get_fact` to call `iter_nodes()` instead of `find_nodes()` → spy records `where=0, limit=0` (no predicates pushed)
- **Original** `get_fact` with `find_nodes()` → spy records `where=6, limit=1` (predicates pushed)
- **Detection**: `test_mutation_unfiltered_iter_nodes_fails` asserts `>=4 where` calls → FAILS under mutation

### Mutation 2: TZ regression
- `test_singapore_tz_affects_naive_timestamp` asserts naive `.timestamp()` in `TZ=Asia/Singapore` gives epoch `1700000000` for UTC+8 local time. Restoring naive `.timestamp()` for UTC interpretation → assertion fails (wrong epoch in Singapore TZ).