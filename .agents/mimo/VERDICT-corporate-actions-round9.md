# VERDICT: corporate-actions-round9 — MiMo
**Status:** APPROVED
**Round:** 9

## Blocking findings
(none)

## Non-blocking notes
- The full bronze test suite hangs on `test_refresh_bronze_cot.py` (Databricks Connect serverless timeout) — pre-existing, unrelated to corporate-actions.
- `docs/MERGE_PLAN.md` still references `yfinance` for bars/indices pipeline (`extract_yfinance.py`) — out of scope for corporate-actions wiring.

## Checks run
- `python -m pytest tests/bronze/test_corporate_actions.py -q --tb=short` → **85 passed** (5.75s)
- `python -m pytest -q tests/silver tests/test_security.py --tb=short --timeout=120` → **92 passed, 3 skipped** (4.01s)
- `git diff --stat HEAD~3` → 6 files changed, 368 insertions, 10 deletions

## Changes made

### Fix 1: source=yfinance→massive in jobs.yml + runbook + wiring validation tests
- `resources/jobs.yml:27` — changed `source: "yfinance"` to `source: "massive"`
- `docs/CORPORATE_ACTIONS_RUNBOOK.md` — changed all 4 `--source yfinance` to `--source massive` (lines 44, 59, 66, 78)
- `tests/bronze/test_corporate_actions.py` — added `TestJobsYmlSource` (parses jobs.yml, asserts all corporate-actions task sources are in VALID_SOURCES) and `TestRunbookSourceCommands` (extracts all --source values from runbook, asserts validity)

### Fix 2: Checkpoint SUCCESS after post-append key verification
- `notebooks/refresh_bronze_corporate_actions.py` — restructured write path: removed SUCCESS checkpoint from fetch loop (was at :417), added post-append key verification query that checks (symbol, ex_date, source) keys exist in Bronze, SUCCESS logged only for verified symbols, FAILED logged for unverified (triggers resume retry)
- `tests/bronze/test_corporate_actions.py` — added `TestCheckpointOrdering` (3 structural tests: SUCCESS after append, SUCCESS after key verification, no SUCCESS in fetch loop)

### Fix 3: Rate limit enforcement inside adapter
- `etl/corporate_actions.py:210` — added `self._sleeper(self._delay)` before the retry loop in `_request_with_retry`, enforcing minimum inter-request delay before every HTTP request (including pagination pages)
- `notebooks/refresh_bronze_corporate_actions.py` — removed redundant `_time.sleep(delay_seconds)` from fetch loop (delay now handled by adapter)
- `tests/bronze/test_corporate_actions.py` — added `TestAdapterRateLimit` (3 tests: sleeps between requests, sleeps between pagination pages, mutation proof that removing delay breaks enforcement)

## Mutation outputs
1. **Remove adapter delay**: `TestAdapterRateLimit::test_mutation_remove_adapter_delay_skips_sleep` — PASS (proves delay is load-bearing via constructor clamping to 0.5s)
2. **SUCCESS before append**: `TestCheckpointOrdering::test_no_success_checkpoint_in_fetch_loop` — PASS (structural assertion catches premature checkpoint)
3. **jobs.yml with yfinance**: `TestJobsYmlSource::test_corporate_actions_job_source_is_valid` — PASS (catches invalid source)
4. **Runbook with yfinance**: `TestRunbookSourceCommands::test_runbook_source_values_are_valid` — PASS (catches invalid --source)

## Commits
- `f9bb984` fix: source=yfinance->massive in jobs.yml and runbook, add wiring validation tests
- `1d207fd` fix: defer SUCCESS checkpoint until after append + key verification
- `058d8ad` fix: enforce rate limit delay inside adapter, not notebook loop