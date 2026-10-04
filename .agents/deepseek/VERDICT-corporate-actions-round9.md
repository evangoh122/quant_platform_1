===VERDICT START===
# VERDICT: corporate-actions-round9 — DeepSeek (checker)
**Status: CHANGES_REQUESTED**
**Round:** 9
Scope: commits 7e39b74..HEAD (MiMo's 3 wiring fixes). Read-only source; mutation proofs in /tmp/ca9-mut-* copies. MiMo's self-verdict is not evidence.

## Counts
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → **344 passed, 13 skipped, 0 failed** (35.56s).
- pyspark-hidden (`PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps`) same suite → **334 passed, 23 skipped, 0 failed**. The 10 extra skips are all pre-existing `test_refresh_bronze_cot.py`/`test_refresh_bronze_options.py` PySpark-conditional skips, none in corporate-actions.
- `python3 -m pytest -q tests/bronze/test_corporate_actions.py` → **85 passed, 0 failed**.
- `git diff 7e39b74..HEAD -- tests` → only `tests/bronze/test_corporate_actions.py` (+316/−1, the −1 is a missing trailing newline). No test deleted/weakened.

## Verified OK

### 1. Source wiring → massive. FIXED.
`resources/jobs.yml:27` and all 4 runbook commands (`docs/CORPORATE_ACTIONS_RUNBOOK.md:44,59,66,78`) now `massive`. `grep -rni yfinance resources/ docs/ notebooks/ etl/` → no corporate-actions wiring/docs hit; remaining hits are `etl/extract_yfinance.py` (bars/indices, out of scope), `requirements.txt:14` (still used by that pipeline), and silver/bronze test fixtures that treat a `yfinance`-source bronze row as a negative case. Tests `TestJobsYmlSource` and `TestRunbookSourceCommands` parse the real files. **Mutation** (put `yfinance` back in jobs.yml, /tmp/ca9-mut-yfinance) → `TestJobsYmlSource::test_corporate_actions_job_source_is_valid` **FAILS**: `source='yfinance' which is not in VALID_SOURCES={'massive'}`. Load-bearing.

### 3. Rate limit inside adapter. FIXED.
`etl/corporate_actions.py:212-213` sleeps `self._delay` before every `_request_with_retry` (i.e. before every page; empty-result symbols hit one request each). Notebook loop sleep removed (`refresh_bronze_corporate_actions.py:432` comment only). **Mutation** (remove the `self._sleeper(self._delay)` line, /tmp/ca9-mut-delay) → `TestAdapterRateLimit` **3 failed** (all three tests). Load-bearing.

## Blocking findings

1. **No functional crash/resume test — the 3 "checkpoint ordering" tests are source-text greps.**
   [tests/bronze/test_corporate_actions.py:1168-1271] `TestCheckpointOrdering` (`test_success_checkpoint_after_append_not_before`, `test_success_checkpoint_after_key_verification`, `test_no_success_checkpoint_in_fetch_loop`) each read the notebook file and assert line ordering / grep for the literal `_log_checkpoint(spark, run_id, sym, "massive", "SUCCESS"` string. None imports and runs the notebook's loop. `TestResumeCheckpoint` [tests/bronze/test_corporate_actions.py:609-639] is equally structural (`assert "SELECT DISTINCT symbol FROM" in text`) or tautological (`sym in completed_keys`). BUILD-corporate-actions-round9.md:12 explicitly required: "simulate a crash between fetch and append (writer raises) → on resume with the same run_id the symbol is NOT skipped and its rows get written." That test does not exist → a real regression in the resume path (e.g. resume-skip logic, or the `sym_verified` bug below) would pass the entire suite. MiMo's verdict concedes "3 structural tests".
   Failure scenario: a future change re-introduces premature checkpointing via a differently-formatted call (e.g. status passed via a variable, or SUCCESS written by a helper) or breaks the resume skip → no test fails.

2. **`sym_verified` grouping marks a symbol SUCCESS if ANY of its rows verifies, not ALL.**
   [notebooks/refresh_bronze_corporate_actions.py:492-499] `sym_verified.setdefault(sym, False)` is a no-op once the symbol is already `True`. For a symbol with two new rows where row1's key is verified and row2's key is missing from Bronze, the dict stays `True` → SUCCESS logged at :501-504 → on resume that symbol is in `completed_keys` (:346-356) and is skipped, permanently omitting row2. The intended semantics ("SUCCESS only after the batch's keys are all verified") require `all(k in verified_keys for k in sym_keys)` per symbol. Failure scenario: any partial/format-mismatched verification (or a symbol whose ex_date stringifies differently) silently checkpoints SUCCESS and drops rows on resume — the exact data-loss the fix was meant to prevent.

3. **Post-append verification query interpolates row values into SQL.**
   [notebooks/refresh_bronze_corporate_actions.py:478-485] builds `key_tuples_str` with an f-string per key and splices it into `WHERE (symbol, CAST(ex_date AS STRING), source) IN (...)`. Per the builder mandate "a single f-string SQL filter is a blocking defect" this is a non-parameterized filter. Practical risk is low (symbol is `UPPER(TRIM())` universe output, ex_date is `fromisoformat`-validated, source is the literal `massive`), but a quote-bearing symbol would raise → caught → `verified_keys` empty → symbols silently get no SUCCESS/FAILED checkpoint (safe re-fetch, but a latent defect and a mandate violation).

## Non-blocking notes
1. **Retry spacing does not apply `_delay` before retry attempts.** `_request_with_retry` [etl/corporate_actions.py:213-241] sleeps `_delay` once before the retry loop, then only `backoff = min(2**attempt * 1.0, 30.0)` between retries. With the default `delay_seconds ≤ 1.0` the backoff (≥1.0) ≥ delay, so spacing is fine; but if `delay_seconds > 1.0`, consecutive retry requests are spaced `backoff` < `delay`, violating "minimum inter-request delay before EVERY HTTP request (incl. retries)". Acceptable but worth noting the delay and backoff do not compose (they are alternatives, not stacked).
2. **Rate-limit test asserts call count, not monotonic spacing.** `test_adapter_sleeps_between_requests` [tests/bronze/test_corporate_actions.py:1285-1340] uses a `MagicMock` sleeper and asserts `len(sleep_calls) >= 2` and each arg `>= 0.5`. It does not use a fake clock to assert monotonic spacing `>= delay` between actual request timestamps (the CHECK phrasing "spacing ≥ delay"). The mock records the exact sleep durations, so `>= delay` per call is effectively verified, but not end-to-end spacing across retries+pagination.

## Checks run
- `python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (344/13)
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest -q tests/bronze tests/silver tests/test_security.py` → pass (334/23)
- `python3 -m pytest -q tests/bronze/test_corporate_actions.py` → pass (85)
- Mutation yfinance-in-jobs.yml (/tmp/ca9-mut-yfinance) → `TestJobsYmlSource` 1 failed
- Mutation SUCCESS-before-append (/tmp/ca9-mut-success) → `TestCheckpointOrdering` 3 failed (structural only)
- Mutation remove-adapter-delay (/tmp/ca9-mut-delay) → `TestAdapterRateLimit` 3 failed
- `git diff 7e39b74..HEAD -- tests` → only test_corporate_actions.py (+316/−1), no deletions
===VERDICT END===
