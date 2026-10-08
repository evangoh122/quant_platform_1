# BUILD — PR #42 round 5: current-main serverless contract failures

You are MiMo. Work only on `feat/xbrl-fundamentals` at or after merge commit
`d07e020`, which merges current `origin/main` into the PR branch. Round 4's
deterministic-worker fix is already approved; preserve it. Fix the four exact
Python CI failures from run `37442951822`, job `112200849281`.

## Required implementation

1. `resources/jobs.yml`
   - Remove the task-level `libraries:` entry from the serverless
     `ingest_sec_companyfacts` task.
   - Keep `pyyaml>=6.0` exactly once under
     `environments[].spec.dependencies` for that job.

2. `pipelines/ingest_sec_companyfacts.py`
   - Replace the bare `__file__` sys.path bootstrap with the repository's
     current serverless-compatible runtime pattern. Reuse
     `pipelines._runtime.repo_root`; do not invent another resolver.
   - Replace both direct `databricks.connect` imports and
     `DatabricksSession.builder.serverless()` calls with
     `pipelines._runtime.get_spark()`.
   - Preserve injected `spark_factory` behavior in both writers.
   - Ensure the module remains importable in offline tests without requiring
     PySpark or databricks-connect at import time.

3. Tests
   - Make all four current-main serverless contract tests pass:
     `test_no_libraries_on_serverless_tasks`,
     `test_no_bare_dunder_file_in_entry_points`,
     `test_no_serverless_session_outside_runtime`, and
     `test_no_databricks_connect_import_outside_runtime`.
   - Add/adjust focused writer tests proving default writer construction calls
     the shared runtime helper while an injected factory is still honored.
   - Preserve all round-4 deterministic-worker tests and proofs.

## Required failing-before and mutation proofs

Use fresh `git archive` copies under `/tmp`.

1. Show the four named current-main contract tests fail on the pre-r5 merge
   head and pass after the fix.
2. Reintroduce task-level `libraries`; the job contract test must fail.
3. Reintroduce bare `__file__`; the entry-point test must fail.
4. Reintroduce a direct `databricks.connect` import/serverless builder in either
   writer; the runtime contract tests must fail.
5. Bypass the shared runtime helper or ignore an injected factory; focused
   writer tests must fail.
6. Retain the round-4 worker-sizing and reservation mutations as passing
   negative controls.

## Acceptance

```bash
python3 -m pytest -q tests/test_jobs_serverless.py
python3 -m pytest -q tests/bronze/test_sec_companyfacts.py
python3 -m pytest -q -m "not spark and not lakebase and not databricks"
git diff --check
```

Use LF endings. Do not change schemas, ingestion semantics, dependencies beyond
the YAML placement correction, `.agents/dispatch.sh`, deployment state, or live
data. Commit intended changes and write
`.agents/mimo/VERDICT-xbrl-pr42-fixes-r5.md` with exact test and mutation
evidence. Do not push, merge, or comment on the PR.
