# VERDICT: lakebase-agent-tools — DeepSeek (Builder)

**Status:** APPROVED (builder self-verdict — independent Codex/Claude validation still required per PROTOCOL)
**Round:** 1
**Branch:** `slice/lakebase-agent-tools` (commit `2f50bb1`); `main` untouched at `1728cb3`

## Blocking findings

None for the slice scope. Two items are flagged for the gate to be aware of,
but neither is a defect in this slice's code:

- The **full-suite** command `pytest tests/ -q` does **not** pass — it has 25
  pre-existing *collection* errors unrelated to this slice (missing `db.database`
  / DuckDB module, `tests/rag/*` importing the old `api.services.*` path,
  missing `rag_engine`, missing `etl.extract_polygon_ticks`, and `pyspark` not
  installed). This is Phase 1/2/5 migration debt, not lakebase-agent-tools.
- `CREATE PUBLICATION` is administratively disabled on this Lakebase instance
  (verified: `CREATE PUBLICATION is not enabled on this Lakebase instance`), so
  the CDC publication/slot must be provisioned by the Databricks Lakebase CDC
  layer (next slice). Documented in `db/migrations/CDC.md`; `REPLICA IDENTITY
  FULL` (the part this slice owns) is set and verified.

## Scope notes (additive decisions)

- `orders.symbol TEXT NOT NULL` was added beyond the literal field list. The
  approve path must re-run concentration/duplicate checks and call the bridge,
  all of which need the symbol; it is not otherwise resolvable when
  `signal_id` is NULL. Additive, documented, indexed.
- Root `conftest.py` now tolerates the removed `db.database` (DuckDB) module so
  the test suite can collect; the DuckDB `tmp_db`/`db_conn` fixtures skip when
  the module is absent.

## Non-blocking notes

- Token is minted on demand via the `databricks` CLI and held only in memory;
  refresh-before-expiry margin 300s. No token/secret is committed (verified by
  `git grep`).
- All SQL is `%s`/`F.col` parameterized. `grep -rn 'f"' agent/ db/ | grep -iE
  'select|insert|update|delete|where'` returns nothing. Remaining f-strings are
  log/error messages and identifier interpolation of constants only.

## Checks run

```
$ python3 -m pytest tests/lakebase/test_guardrails.py tests/lakebase/test_symbol_validation.py -q -m "not lakebase"
...............................                                          [100%]
31 passed in 0.18s
```

```
$ python3 -m pytest tests/lakebase/ -q -m lakebase
...............                                                          [100%]
15 passed, 31 deselected in 52.47s
```

```
$ python3 -m pytest tests/lakebase/ -q
..............................................                           [100%]
46 passed in 54.35s
```

```
$ python3 -m pytest tests/ -q
... (25 collection errors: db.database, rag_engine, api.services.*, etl.extract_polygon_ticks, pyspark) ...
25 errors in 3.07s   # pre-existing, out of this slice's scope
```

### Index proof (EXPLAIN, `SET enable_seqscan = off`)

```
open-orders:         Index Scan using idx_orders_user_symbol_side_status (user_id prefix + status filter)
duplicate-detection: Index Scan using idx_orders_user_symbol_side_status (all 4 cols as Index Cond)
executions-by-order: Bitmap Index Scan on idx_executions_order
research-notes:      Index Scan using idx_research_notes_user_symbol
watchlists:          Bitmap Index Scan on watchlists_user_symbol_uq (user_id prefix)
positions:           Bitmap Index Scan on positions_pkey (account_id prefix)
```

## Acceptance criteria

1. Migration applies against live Lakebase; all 8 tables + constraints + indexes
   verified → pass (`test_migrations.py`, 5/5).
2. No f-string SQL in `agent/` `db/` → pass.
3. No stub remains in `agent/tools_write.py` — all six tools do real I/O; every
   one round-trips in `test_tools_write.py` → pass.
4. Slice tests pass with pasted output above → pass. (Full `tests/` blocked by
   pre-existing Phase 1/2/5 collection debt, not this slice.)
5. No secret committed → pass (`git grep -iE 'eyJ|BEGIN (RSA|PRIVATE)'` → empty).
6. Branch `slice/lakebase-agent-tools` has the commit; `main` untouched → pass.
