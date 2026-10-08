# BUILD — PR #42 round 6: prove default writers use shared runtime

You are MiMo. Work only on `feat/xbrl-fundamentals` at or after
`9122cf636aab0895dca94fa88f61f3d71334a734`. Kimi approved the r5 production
fixes but returned CHANGES_REQUESTED for one missing behavioral proof. Keep this
round test-only unless a minimal production adjustment is strictly required.

## Required changes

In `tests/bronze/test_sec_companyfacts.py`, add focused tests for both:

- `SparkCompanyFactsWriter()` with no `spark_factory`; and
- `SparkCompanyFactsManifestWriter()` with no `spark_factory`.

Each test must monkeypatch `pipelines.ingest_sec_companyfacts.get_spark` with a
spy/fake, exercise `_get_spark()` or an appropriate public path, and prove the
default writer calls and returns the shared runtime helper. Preserve existing
tests proving an explicitly injected `spark_factory` takes precedence.

Do not copy the production branch logic into the tests and do not merely scan
source text.

## Required mutation proof

In a fresh `git archive` copy under `/tmp`, replace either writer's default
`return get_spark()` path with this behaviorally different implementation:

```python
from pyspark.sql import SparkSession
return SparkSession.builder.getOrCreate()
```

The new focused test for that writer must fail. Repeat for both writers or use a
parameterized test that independently identifies each bypass.

Also rerun the r5 contract and regression suites to ensure no loss of coverage.

## Acceptance

```bash
python3 -m pytest -q tests/test_jobs_serverless.py
python3 -m pytest -q tests/bronze/test_sec_companyfacts.py
python3 -m pytest -q -m "not spark and not lakebase and not databricks"
git diff --check
```

Use LF endings. Do not modify `.agents/dispatch.sh`, production semantics,
schemas, YAML, dependencies, deployment, or live data. Commit intended changes
and write `.agents/mimo/VERDICT-xbrl-pr42-fixes-r6.md` with exact test and
mutation evidence. Do not push, merge, or comment on the PR.
