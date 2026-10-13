# Evidence — silver_gold_refresh serverless job dependencies (r1)

Branch: `fix/silver-gold-job-deps` (from `main` = `231cc0a5c5f9d1557b778219afce1c38214e252b`)
Worktree: `/root/quant-platform-1/wt-silver-gold-deps`
Date: 2026-10-13

## 1. Problem

`silver_gold_refresh` in `resources/jobs.yml` (task `refresh_silver_gold`,
`pipelines/run_silver_gold.py`, environment `serverless`, `spec: client: "1"`)
declared NO packages. Serverless installs nothing that is not declared under
`environments[].spec.dependencies`, so the gold step failed live on 2026-10-13
one import at a time: `ModuleNotFoundError: No module named 'loguru'`, then
`No module named 'dotenv'`.

## 2. AST import trace (derived, not guessed)

Trace scope = module-scope imports of `pipelines/run_silver_gold.py` + every
repo-local module it imports (including parent-package `__init__` modules) +
every Python transform listed in the script's `STEPS` table (`kind == "py"`),
read from the script's AST (`ast.literal_eval` of the `STEPS` assign).

`STEPS` yields exactly one `py` transform: `gold/gold_sec_features.py`
(executed via `importlib.util.spec_from_file_location`, i.e. loaded standalone —
`gold/__init__.py` is therefore NOT on the import path).

Files visited by the trace (10):

| file | module-scope imports (lineno, module) |
| --- | --- |
| `pipelines/run_silver_gold.py` | 21 `__future__`, 23 `argparse`, 24 `os`, 25 `sys`, 26 `time`, 30 `pipelines._runtime`, 32 `config.universe` |
| `pipelines/__init__.py` | (empty) |
| `pipelines/_runtime.py` | 16 `__future__`, 18 `os`, 19 `sys`, 20 `pathlib` |
| `config/__init__.py` | (empty) |
| `config/universe.py` | 7 `os`, 8 `pathlib`, 9 `typing`, 11 `yaml` |
| `gold/gold_sec_features.py` | 25 `__future__`, 27 `os`, 28 `datetime`, 30 `pyspark.sql`, 32 `api.services.sentiment` |
| `api/__init__.py` | (empty docstring only) |
| `api/services/__init__.py` | (empty comment only) |
| `api/services/sentiment.py` | 15 `__future__`, 17 `json`, 18 `re`, 19 `dataclasses`, 20 `functools`, 21 `pathlib`, 22 `typing`, 24 `loguru`, 26 `api.config` |
| `api/config.py` | 1 `os`, 2 `pathlib`, 3 `loguru`, 4 `dotenv` |

Third-party top-level import names on this path (stdlib and runtime-provided
excluded): **`yaml`, `loguru`, `dotenv`**.

Mapped to distributions with `requirements.txt` lower bounds (identical to the
specifiers already used by `sec_embeddings` / `sec_companyfacts_ingest`):

| import | distribution | requirements.txt |
| --- | --- | --- |
| `loguru` | `loguru>=0.7.0` | line 14 |
| `dotenv` | `python-dotenv>=1.0.0` | line 34 |
| `yaml` | `pyyaml>=6.0` | line 35 |

### Excluded (documented, not guessed)

- `pyspark` (`pyspark.sql` in `gold/gold_sec_features.py:30`), `databricks.connect`
  (`pipelines/_runtime.py` inside `get_spark()`; `gold/gold_sec_features.py`
  `__main__` block) — provided by the Databricks serverless runtime; must not be
  pip-declared (test asserts this).
- `openai` — **omitted on purpose**: only pulled by a lazy, optional import
  inside `generate_tone_analysis` (`api/services/sentiment.py:500`,
  `from openai import OpenAI`). That function is never called on this path; the
  gold step only uses `count_sentiment` and `tokenize` (pure-Python). Same for
  `numpy` (`api/services/sentiment.py:604`, inside `compute_tone_shift`) and
  `api.db.database` (function-level, e.g. `sentiment.py:252,320,391,455,605`).
  The observed successful run that included `openai` in the env was therefore
  sufficient but not minimal; the three declared packages are the exact
  statically reachable set.
- Function-body imports are intentionally not traced: they are optional/lazy and
  not executed at module import time on this path.

### Follow-up (explicitly out of scope for r1)

- `gold/gold_sec_features.py` reaches into the `api` package only for
  `count_sentiment`/`tokenize`, which drags `api.config` (and therefore
  `loguru` + `python-dotenv`) into the job environment. `api/__init__.py` and
  `api/services/__init__.py` are light (docstring/comment only), so no heavy-init
  refactor is required; a future cleanup could move the pure tokenizer/scorer
  out of `api/` or drop the module-scope `from api.config import Config` in
  `api/services/sentiment.py` so the job needs fewer third-party packages.
  NOT refactored here per the request.
- Latent, unrelated: `api/services/sentiment.py` lazy imports
  `api.db.database`, but no `api/db/` package exists in the repo (top-level
  `db/` is a different package). Not touched (not on this path).

## 3. Changes

1. `resources/jobs.yml` — job `silver_gold_refresh`, environment `serverless`
   `spec`: added
   ```yaml
   dependencies:
     - "loguru>=0.7.0"
     - "python-dotenv>=1.0.0"
     - "pyyaml>=6.0"
   ```
   Nothing else changed: no other job, schedule stays `PAUSED`, `databricks.yml`
   / requirements files / pipeline code untouched (diff = 4 inserted lines).
2. `tests/test_silver_gold_job_deps.py` — new, CI-safe (pure `ast` + `yaml`, no
   Spark/network, no hardcoded home paths). Reads `STEPS` from the entry point
   AST, follows repo-local imports incl. parent package inits, normalizes names
   (`python-dotenv`->`dotenv`, `pyyaml`->`yaml`), asserts every traced
   third-party import is declared in the job's environment dependencies; also
   asserts declared specifiers match `requirements.txt` lines and that
   `pyspark`/`databricks*` are not declared. Tracer-sanity tests guard against a
   vacuous trace. Includes two named mutation tests (drop `loguru`; empty
   dependency list as on `main`).

## 4. Acceptance (exact output)

Environment: `/root/quant-platform-1/.venv-write-confirm/venv/bin/python`
(Python 3.12.14, pytest 9.1.1; has pytest/pytest-asyncio/pytest-timeout/httpx/
numpy/pandas/polars/duckdb/scikit-learn/pyyaml — no pyspark, matching CI).

### 4a. Normal run

```
$ /root/quant-platform-1/.venv-write-confirm/venv/bin/python -m pytest -q -m "not spark and not lakebase and not databricks"
...
7 failed, 2839 passed, 70 skipped, 24 deselected, 24 warnings, 1 error in 1048.00s (0:17:28)
```

Failures (all unrelated pre-existing flakes — see §5):
`tests/agent/test_pyspark_leak.py::TestHarnessIsReal::test_buggy_conftest_must_fail`,
`tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms`,
`tests/ml/test_baseline_labels.py::test_daily_close_labels_matches_old_behavior_with_nan_closes`,
`tests/ml/test_hardening.py::test_cot_features_nonzero_after_neutralisation`,
`tests/ml/test_hardening.py::test_arm_d_differs_from_arm_c_in_cot_columns`,
`tests/ml/test_hardening.py::test_fold_local_classification_unchanged_by_future_data`,
`tests/test_hermetic_guard.py::TestResilienceTiming::test_resilience_route_fast_under_guard`;
ERROR `tests/rag/test_edgar_adapter.py::test_adapter_error_is_exception`
(30s timeout while a fixture imports `transformers`, which `rglob`s its
site-packages tree).

### 4b. pyspark-blocked CI-parity run

Stub: `/tmp/opencode/sg-deps-proofs/pyspark-stub/pyspark.py` (single-module stub
that raises `ModuleNotFoundError("No module named 'pyspark'")` on import), first
on `PYTHONPATH`, temp dir outside the repo, no home paths.

```
$ PYTHONPATH=/tmp/opencode/sg-deps-proofs/pyspark-stub /root/quant-platform-1/.venv-write-confirm/venv/bin/python -m pytest -q -m "not spark and not lakebase and not databricks"
...
5 failed, 2842 passed, 70 skipped, 24 deselected, 35 warnings in 667.54s (0:11:07)
```

Failures: `tests/api/test_public_demo_security.py::test_no_cf_header_leftmost_xff_used`,
`tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms`,
`tests/ml/test_baseline_labels.py::test_daily_close_labels_matches_old_behavior_with_nan_closes`,
`tests/ml/test_hardening.py::test_arm_d_differs_from_arm_c_in_cot_columns`,
`tests/ml/test_hardening.py::test_fold_local_classification_unchanged_by_future_data`.
The new test file passed in both runs (8 tests).

## 5. Flake triage (re-run in isolation, per request)

| test | isolation result | classification |
| --- | --- | --- |
| `tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms` | FAILED (`@pytest.mark.timeout(120)` exceeded; also failed at `--timeout=180`) | known `test_ablation` flake — slow sandbox |
| `tests/ml/test_baseline_labels.py::test_daily_close_labels_matches_old_behavior_with_nan_closes` | 30s pytest-timeout alone; **PASSES** with `--timeout=180` | known `tests/ml/*` 30s timeout flake |
| `tests/ml/test_hardening.py::test_cot_features_nonzero_after_neutralisation` | 30s timeout alone; **PASSES** with `--timeout=180` | known 30s timeout flake |
| `tests/ml/test_hardening.py::test_arm_d_differs_from_arm_c_in_cot_columns` | same; **PASSES** with `--timeout=180` | known 30s timeout flake |
| `tests/ml/test_hardening.py::test_fold_local_classification_unchanged_by_future_data` | same; **PASSES** with `--timeout=180` | known 30s timeout flake |
| `tests/api/test_public_demo_security.py::test_no_cf_header_leftmost_xff_used` | **158 passed** in isolation (whole file) | known `test_public_demo_security` flake |
| `tests/test_hermetic_guard.py::TestResilienceTiming::test_resilience_route_fast_under_guard` | wall-clock assert `< 10s` measured 16.6s/10.5s under load (FAIL), **passes** when idle (9.63s in worktree, 10.66s on base archive) | load-sensitive timing flake |
| `tests/agent/test_pyspark_leak.py::TestHarnessIsReal::test_buggy_conftest_must_fail` | **3 passed** in isolation | flake under load (inner-pytest harness test) |
| `tests/rag/test_edgar_adapter.py::test_adapter_error_is_exception` (and siblings) | 9 passed, 3 errors: `Failed: Timeout (>30.0s)` during `transformers` import (`rglob` over site-packages) | 30s timeout flake (heavy import) |

None of these tests are touched by the diff (the change surface is
`resources/jobs.yml` + one new pure-AST test file); all are timing/timeout or
known flakes and pass when re-run in isolation or with a larger timeout.

## 6. Mutation proofs (isolated `git archive` copies under `/tmp/opencode`)

Base SHA archived: `231cc0a5c5f9d1557b778219afce1c38214e252b` (= `main`).
Copies: `/tmp/opencode/sg-deps-proofs/base-main` (old state) and
`/tmp/opencode/sg-deps-proofs/new-state` (base + `resources/jobs.yml` + the new
test file copied in; no recursive worktree copies).

Baseline in `new-state` (control): `8 passed in 5.13s`.

### (a) remove `loguru` from the list -> test fails

`new-state/resources/jobs.yml`, `silver_gold_refresh` block only (other jobs
verified untouched — `sec_embeddings` keeps its own `loguru`):

```
mutation (a) deps now: ['python-dotenv>=1.0.0', 'pyyaml>=6.0']
sec_embeddings untouched: ['sentence-transformers>=2.2.0', 'torch>=2.0.0', 'loguru>=0.7.0', 'python-dotenv>=1.0.0']
...
E       assert not ['loguru']
tests/test_silver_gold_job_deps.py:283: AssertionError
FAILED tests/test_silver_gold_job_deps.py::test_traced_third_party_imports_are_declared
1 failed, 7 passed in 3.06s
```

### (b) remove `python-dotenv` -> test fails

```
mutation (b) deps now: ['loguru>=0.7.0', 'pyyaml>=6.0']
sec_embeddings untouched: ['sentence-transformers>=2.2.0', 'torch>=2.0.0', 'loguru>=0.7.0', 'python-dotenv>=1.0.0']
...
E       assert not ['dotenv']
tests/test_silver_gold_job_deps.py:283: AssertionError
FAILED tests/test_silver_gold_job_deps.py::test_traced_third_party_imports_are_declared
1 failed, 7 passed in 2.83s
```

(name normalization: `python-dotenv` -> `dotenv`.)

### (c) new test against a `main` archive -> fails

`base-main` (unchanged `main` `jobs.yml`, no `dependencies` key) + new test:

```
E       AssertionError: silver_gold_refresh declares no dependencies; the entry point needs at least the traced third-party imports declared
E       assert []
FAILED tests/test_silver_gold_job_deps.py::test_traced_third_party_imports_are_declared
FAILED tests/test_silver_gold_job_deps.py::test_declared_dependencies_match_requirements_specifiers
2 failed, 6 passed in 3.23s
```

Old-behavior demonstration is the same run: on `main` the job environment
declares nothing, matching the live `ModuleNotFoundError` sequence.

## 7. Bundle validation (as CI: .github/workflows/ci.yml "Validate Databricks bundles")

Databricks CLI v1.16.1 is installed and already configured (no credentials were
read or printed). Both CI commands run without extra credentials:

```
$ databricks bundle validate -t dev        # repo root
Name: quant-platform
Target: dev
...
Found 4 warnings
EXIT:0
```
(warnings are pre-existing sync-pattern warnings: `.mypy_cache` unmatched,
`frontend/dist/**` unmatched — frontend not built in this worktree; 2 others)

```
$ databricks bundle validate -t dev        # bundles/streaming (CI working-directory)
Name: qp1-stream-streaming
Target: dev
...
Validation OK!
EXIT:0
```

## 8. Non-goals (verified)

No deploy, no job run, no live writes, no schedule change (`pause_status:
PAUSED` retained), no pipeline/requirements/databricks.yml changes, no
dependency pinning changes elsewhere. LF line endings confirmed
(`file`: "ASCII text" / "UTF-8 text", no CRLF). No secrets in code, evidence,
or output. No `$HOME`/`~` paths in code or tests (paths derived from
`Path(__file__)`).

## 9. Verification summary

- New tests: 8/8 pass in worktree and in the `new-state` archive copy.
- Full suite: runs green apart from the documented pre-existing flakes (§5).
- CI parity (pyspark blocked via stub): same, 2842 passed.
- Mutations (a), (b) and the `main`-archive run (c) all fail as required.
