# VERDICT: bronze-equities — DeepSeek (checker)

===VERDICT START===

**Status:** APPROVED
**Round:** 1

## Checks performed

### 1. Append-only in every path; anti-join on the full natural key — PASS
- The only writes to the Bronze market tables are
  `new_rows.write.format("delta").mode("append").saveAsTable(target)`
  (notebooks/refresh_bronze_equities.py:496). A grep for `overwrite|replaceWhere|MERGE|UPDATE|DELETE|spark.sql` finds no such pattern against Bronze tables; the sole `UPDATE` is `DeltaTable.forName(...).update(...)` scoped to the operational ingestion-log table (notebooks/refresh_bronze_equities.py:382), which the spec explicitly permits.
- There is no first-time table-creation path in this notebook (the Bronze and log tables are assumed to exist and are read via `spark.table(...)`), so no `overwrite`/`replaceWhere` first-load path exists either.
- Anti-join uses the full natural key `KEY_COLUMNS = ["symbol", "event_ts", "timespan"]`
  (notebooks/refresh_bronze_equities.py:52) in
  `incoming.join(existing_keys, KEY_COLUMNS, "left_anti")`
  (notebooks/refresh_bronze_equities.py:479), preceded by
  `incoming.dropDuplicates(KEY_COLUMNS)` (notebooks/refresh_bronze_equities.py:476).
  Matches the spec's minute/day key `(symbol, event_ts, timespan)`. `source_file` is lineage only, correctly excluded from the key.

### 2. SUCCESS only after rows land + verification — PASS
- `log_finish(..., None)` (marks SUCCESS) is reached only after
  `new_rows.write...append` and the post-write verification
  `in_target = spark.table(target).filter(F.col("source_file") == key).count()` with
  `if in_target < new_count: raise RuntimeError(...)`
  (notebooks/refresh_bronze_equities.py:502-513). Any exception in the append/verify path is caught and routed to `log_finish(..., exc)` → FAILED, never SUCCESS.
- A zero-`new_count` file (fully anti-joined already) correctly skips the write and is marked SUCCESS only after the verification passes — idempotent retry.

### 3. Timestamps not altered in Bronze — PASS
- Bars are stamped from the source start time: `event_ts = ns_to_ts(r.get("window_start"))`
  (notebooks/refresh_bronze_equities.py:140 for minute, :176 for day). No shift to ingestion/availability time; `ingest_ts` is a separate column (`_now_utc()`, :214). `ns_to_ts` preserves the exact epoch instant (only drops tzinfo to naive UTC, which is how Spark TimestampType stores it); no bar time is rewritten.

### 4. Credentials from `evangoh_capstone`, never printed/logged — PASS
- Read via `dbutils.secrets.get(scope="evangoh_capstone", key="massive_s3_access_key"/"massive_s3_secret_key")`
  (notebooks/refresh_bronze_equities.py:290-291). A grep of `print(...)` shows only
  prefix-skip notices, cache-size counts, and the JSON report (no secret values, no prefixes/lengths, no client objects). The per-file error status records only `type(exc).__name__` (:460, :518); log error messages truncate `str(error)[:4000]` (:373) but boto3 `ClientError` strings do not echo authorization headers. `_is_forbidden` (:199) inspects the message string but never prints the exception body.

### 5. Tests call production functions, but do NOT cover dedup/anti-join — NOTE (gap)
- Tests import the real module via importlib and exercise the pure helpers directly
  (`ns_to_ts`, `as_float`, `as_int`, `parse_object_key_date`, `key_in_window`, `parse_minute_file`, `parse_day_file`) — tests/bronze/test_refresh_bronze_equities.py:23-36.
- They would **not** fail if the dedup/anti-join broke, because `dropDuplicates` and the `left_anti` join live inside `main()`'s nested `run_dataset`, which the unit tests never invoke. Proven by mutation under `/tmp`: a copy with both
  `incoming.dropDuplicates(KEY_COLUMNS)` and the `left_anti` join removed still yields
  `10 passed` (see "Checks run"). This is consistent with the BUILD spec's explicit test scope ("self-contained … pure parsing/key-selection helpers"), and the anti-join correctness was verified operationally (coordinator live run: written deltas match dry-run, zero duplicate keys in the new period). No automated regression guard exists for the core idempotency mechanism — flagged for the coordinator, not treated as blocking per spec scope.

### 6. Re-run safety — PASS
- On a second `--write`, `already_ingested` (notebooks/refresh_bronze_equities.py:341-351)
  matches `(source_file, dataset)` against `status = SUCCESS`, so every completed file is skipped and 0 rows are appended. Even if the log skip were bypassed, the anti-join against the now-populated key set reduces every file's `new_count` to 0.

## Non-blocking notes

- [notebooks/refresh_bronze_equities.py:433-439] The anti-join key set is pruned to `event_ts >= start_date - 2 days` for performance. This is safe for the expected data (incoming file dates are `>= start_date`, so all incoming `event_ts` fall inside the buffered window), but the invariant "file-date >= start_date ⇒ event_ts >= start_date − 2 days" is implicit, not asserted.
- [notebooks/refresh_bronze_equities.py:434-440] `existing_keys` is materialized via `count()` but not `.cache()/persist()`; correctness is unaffected (deterministic re-evaluation), only a potential re-scan cost per file remains (Delta block cache mitigates).
- Pre-existing data issue (out of scope, from MiMo verdict): `bronze_ohlcv` holds ~5.7M duplicate groups from an earlier loader mixing `day` bars into the minute table. This refresh's anti-join cannot create new duplicates and is not responsible for the historical ones.

## Checks run

- `python3 -m pytest tests/bronze/test_refresh_bronze_equities.py -q` → `10 passed in 0.06s`
- Mutation proof (dedup/anti-join removal under `/tmp/mutant-test`, worktree untouched):
  `python3 -m pytest tests/bronze/test_refresh_bronze_equities.py -q` → `10 passed in 0.14s`
  (confirms the tests do not detect a broken anti-join/dedup).
- `grep -nE 'overwrite|replaceWhere|MERGE|UPDATE|DELETE|spark\.sql' notebooks/refresh_bronze_equities.py` → no Bronze-write violations (only the permitted log-table `UPDATE`).
- `grep -nE 'mode\(|saveAsTable' notebooks/refresh_bronze_equities.py` → only `mode("append")`.

===VERDICT END===
