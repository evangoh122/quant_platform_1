# BUILD — PR #42 CodeRabbit r4: deterministic ingestion workers

You are MiMo. Work only on `feat/xbrl-fundamentals` at or after PR #42 head
`74ca16e35cb67cc4cdcd12121479064bfc3fd773`. This round fixes the one remaining
current CodeRabbit finding. Do not rework the already-approved schema helpers,
reservation protocol, manifest migration, or job dependencies.

## Required implementation

1. `pipelines/ingest_sec_companyfacts.py:460-592`
   - Add a keyword-only `max_workers: int = 4` argument to
     `run_ingest_companyfacts`.
   - Reject values below 1 with `ValueError("max_workers must be >= 1")`.
   - Derive a separate local `worker_count` as
     `min(max_workers, len(ticker_cik_pairs))` when pairs exist, otherwise `1`.
   - Pass `worker_count` to `ThreadPoolExecutor`; do not shadow the input.

2. `tests/bronze/test_sec_companyfacts.py:811-1021`
   - Pass `max_workers=1` to the retry/attempt-count test and the
     failed-first-write recovery test, whose assertions require deterministic
     ordering. Correct their docstrings.
   - Pass `max_workers=2` explicitly to the concurrent duplicate-reservation
     test so it continues exercising the race guard.
   - Add a test that spies on `ThreadPoolExecutor`, calls production
     `run_ingest_companyfacts(..., max_workers=1)`, and asserts one worker was
     requested. It must fail on the current PR head with an unexpected keyword
     argument.
   - Add coverage that `max_workers=0` raises the specified `ValueError`.

## Required proofs

Use fresh `git archive` copies under `/tmp`.

1. Before the fix, the new one-worker contract test fails.
2. After the fix, mutate executor sizing back to `min(4, len(...))`; the
   executor-spy test fails.
3. Move reservation ownership back after the Delta append; the existing
   two-worker exact-one-append test fails.
4. Run each order-dependent test 30 consecutive times with zero failures.

## Acceptance

```bash
python3 -m pytest -q tests/bronze/test_sec_companyfacts.py
for i in $(seq 30); do
  python3 -m pytest -q tests/bronze/test_sec_companyfacts.py \
    -k "first_write_failure_allows_second_write or duplicate_manifest_attempt_count_with_retries" || exit 1
done
python3 -m pytest -q -m "not spark and not lakebase and not databricks"
git diff --check
```

Use LF endings. Do not touch `.agents/dispatch.sh`, access Databricks, push,
merge, or comment on the PR. Stage only intended files, commit on the requested
branch, and write `.agents/mimo/VERDICT-xbrl-pr42-fixes-r4.md` with the commit,
commands, failing-before proof, and mutation failures. MiMo's verdict is a
self-report; Kimi and Codex must independently validate the result.
