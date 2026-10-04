===VERDICT START===
Reviewer: Claude Sonnet subagent (stopgap for Codex, usage-limited)
Status: CHANGES_REQUESTED

Tests: `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` -> 359 passed, 13 skipped (all skips are the pre-existing "DuckDB removed" skips). Scope: git diff origin/main...HEAD at d2684b8.

## Findings

1. BLOCKER (scheduled job) - resources/jobs.yml:21-27 / notebooks/refresh_bronze_corporate_actions.py:1.
   The job uses `notebook_task` with `notebook_path: ../notebooks/refresh_bronze_corporate_actions.py`, but the file starts with a `"""` docstring, not `# Databricks notebook source`. Every other file used as a notebook in this repo (01_ingest_market_data.py, 02_ingest_sec_edgar.py, refresh_bronze_equities.py) has that header. Without it the bundle syncs the file as a plain workspace file, not a notebook, so `notebook_task` fails at deploy or first run, and `dbutils` / widgets are never injected. This is the only notebook_task in jobs.yml (the others are spark_python_task). Fix: make `# Databricks notebook source` line 1 (docstring may follow), and add a test asserting the first line. Alternative: switch the task to `spark_python_task` with `parameters:` (CLI path already exists).
   Not verified live (no Databricks access from my sandbox); this is from repo convention plus DAB behavior, so Claude should confirm with `databricks bundle validate` / a dry-run job run.

2. Non-blocking (job default) - resources/jobs.yml:25-28: `mode: "dry-run"` and no `schedule:` block. The job writes nothing unless the operator overrides mode=write. Fine as a safety default, but it is not a "scheduled" refresh; state this in the runbook or add a PAUSED schedule like silver_gold_refresh.

3. Non-blocking, TEST GAP (two surviving mutations) - silver/08_silver_ohlcv_day_adjusted.sql:199 and :204.
   Mutation A: adj_close `close * (1/cum)` -> `close * cum` : tests/silver all 92 passed (SURVIVED).
   Mutation B: adj_volume `volume * cum` -> `volume / cum` : 92 passed (SURVIVED).
   tests/silver/test_ohlcv_day_adjusted.py exercises Python re-implementations (`_adj_volume`, line 42), not the SQL `_adjusted` view; the DuckDB semantic tests only execute `_massive_splits`, `_split_factors` and the break views. The adj_* price/volume expressions are therefore unguarded. The SQL is CORRECT today (see 5), so I did not make this a blocker, but it is the central deliverable: add one DuckDB test that runs `_adjusted` on a 2-split + reverse-split fixture (my probe is a ready template: /tmp/rv4/probe2.py) and asserts adj_close, adj_volume, price_adjustment_factor.
   Mutation C (killed): `s.ex_date > d.event_date` -> `>=` in a copy: 4 failures in tests/silver (strict ex-date boundary is protected).

4. Round-3 blocker re-probed (own harness /tmp/rv4/probe1.py, fakes for Writer/CheckpointStore/KeyVerifier):
   - Existing key present, no prior SUCCESS: run_batch wrote 0 rows, logged SUCCESS. FIXED.
   - Second resume with same run_id: adapter fetch count stayed 1 (symbol skipped). FIXED.
   - Same key, DIFFERENT ratio (true conflict): ALSO logged SUCCESS. This contradicts the task-brief expectation ("not marked SUCCESS"). Cause: key is (symbol, ex_date, source) and SparkKeyVerifier (:254-285) joins on key only. It matches the documented design (first-write-wins, DeepSeek r11 verdict item 2; conflict_rows is counted in the report), so I treat it as non-blocking, but SUCCESS here means "keys present", not "ratio agrees"; a Massive ratio revision stays silently stale in bronze and silver. Recommend runbook text + alerting on `conflict_rows > 0`.

5. Adjustment math (silver/08) - verified with my own DuckDB run of the real `_massive_splits`/`_split_factors`/`_adjusted` views:
   fixture T: 2:1 on d3 and 3:1 on d6, flat true price 100 -> cum ratio 6/6/3/3/3/1/1, adj_close 100 on all bars, adj_volume 60 on all bars, adjusted returns 0.
   fixture R: reverse 0.1 on d4 -> cum 0.1 pre-split, adj_close 100 throughout, adj_volume 100.
   Direction (divide price by product of later ratios, multiply volume), multi-split product, reverse split and ex-date-bar-on-new-basis are all correct. LIVE: AMZN 2022-06-06 +1.99% consistent.
   PIT note (non-blocking, documented in the SQL header): adj_* are current-scale and restate whenever a future split lands, while `information_available_ts` is bar-date 16:30 ET; they are return-safe but not valid as historical price-level features. Make sure gold does not consume adj_close as a level feature.
   Minor: data_quality_breaks rows are never deleted/reclassified-to-gone if a candidate stops qualifying (MERGE has no WHEN NOT MATCHED BY SOURCE); stale masked rows can persist. Acceptable given the manual-review preservation intent.

6. Secrets - OK. etl/corporate_actions.py redacts apiKey in logged URLs (:99-102, :210); run_batch redacts exceptions before print and before writing `error_text` (:362, :381); no prints of the key; key not written to any table. `_resolve_cli_api_key` (:95-111) base64-decodes the SDK value and prefers MASSIVE_API_KEY plaintext; notebook mode uses `dbutils.secrets.get` (plaintext, correct). Minor: run_id is interpolated into SQL in SparkCheckpointStore.completed_symbols (:247) and main (:~627); run_id is operator-supplied via widget/CLI, so low risk, but use a parameterized/escaped value.

7. Idempotency - OK. Bronze: anti-join on (symbol, ex_date, source) + append only for new keys, deferred SUCCESS after key verification; write failure logs FAILED for all pending symbols. Silver: MERGE on (symbol, event_date) with matched UPDATE of all columns and explicit column lists in every INSERT/UPDATE; breaks MERGE preserves reviewed rows (`reviewed_by IS NULL`). pipelines/run_silver_gold.py runs the 08 file twice (steps silver_ohlcv_day_adjusted and data_quality_breaks, :50-51); this is redundant but idempotent, and `data_quality_breaks` is excluded from TRUNCATE (:92-99). Note the SQL file has the table-creating DDL and both MERGEs executed in the first step, so the second is wasted work (~double runtime), not a correctness problem.

## Counts
Tests 359 pass / 13 skip / 0 fail. Mutations: 3 run (1 killed, 2 survived). Blockers: 1 (finding 1). Live evidence from the brief (514 split rows / 261 symbols / 639,369 silver rows / 237 breaks: 63 explained, 174 masked) not re-run by me (no network).

Recommendation: fix finding 1 (one-line header + test); findings 3 and 2 are strongly recommended but may go with the PR if the owner agrees.
===VERDICT END===
