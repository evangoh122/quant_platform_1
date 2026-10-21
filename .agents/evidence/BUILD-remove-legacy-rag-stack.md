# BUILD-remove-legacy-rag-stack — implementation evidence (DeepSeek V4.1 Flash 1017)

- **Request:** `.agents/requests/BUILD-remove-legacy-rag-stack.md`
- **Facts read:** `.agents/requests/FACTS-uc-rag-tables-2026-10-22.md`
- **Worktree / branch:** `/home/jianj/code/wt-rag-p0`, `chore/remove-legacy-rag-stack`
- **Base:** `0dc5b1c3e4598a6ea2c3b22f28cac7125da4b123` (`origin/main`)
- **Code commit:** `fb713ed28f120b1f9d09bf40fd9b4e273bbe1fea`
  (tree `b306a5582a6e04c8f591c00f929d4d6f82486d2c`). This evidence file is
  committed on top of that commit; the SHA in the `BUILD DONE` line is the
  branch head to validate.
- **Environment:** WSL Ubuntu, CPython 3.12.3, pytest 9.1.1, FastAPI 0.142.2,
  pydantic 2.13.5, starlette 1.7.0, httpx 0.28.1.
  **Deviation from the request's acceptance recipe:** `uv` is not installed in
  this environment (`command -v uv` → nothing). The acceptance command was run
  with `python3 -m pytest` against the already-provisioned interpreter that has
  `requirements.txt` + `requirements-dev.txt` + the CI extras installed
  (`mlflow`, `pytest-timeout`, `httpx`, `numpy`, `pandas`, `polars`, `duckdb`,
  `scikit-learn`, `pyyaml`); `pytest-asyncio` and `evidently` are absent, no
  test in the selected suite needs them. No repository file was changed to work
  around this.
- **Line endings:** every new/changed file is LF (`grep -q $'\r'` clean for all
  eight touched files).

---

## 1. What was deleted (52 files, 11,900 lines)

Derivation: `python3 -I .agents/requests/reachability_graph.py <archive>` on an
`origin/main` archive reported 41 unreachable `api.*` modules (25 reachable).
Re-running the same logic with the package-`__init__` exemption implemented in
`scripts/check_api_reachability.py` reports **40** dead modules at
`origin/main` (65 api modules, 25 reachable) and **0** at HEAD (25 api modules,
25 reachable). The exempted one is `api.services` — a package init whose
submodules are live (`import api.services.x` never names the package).

Every deletion was confirmed with `git grep -w` across the whole tracked tree
(Python, YAML, notebooks, docs, frontend strings) before `git rm`:

```text
$ git grep -w <module>   # e.g. langgraph_engine, runtime_snapshot, chat_engine, ...
```

The only non-archive occurrences were the deleted modules themselves, their
own tests, the modules that imported them (also deleted), and the two prose
mentions fixed in §4.

### 1a. Deleted `api/` modules (40 files, 8,141 lines)

| lines | file |
| ---: | --- |
| 11 | `api/models/__init__.py` |
| 108 | `api/models/eval_types.py` |
| 48 | `api/models/review_schemas.py` |
| 193 | `api/models/schemas.py` |
| 22 | `api/services/_edgar_identity.py` |
| 143 | `api/services/calibration.py` |
| 302 | `api/services/chart_tool.py` |
| 183 | `api/services/chat_engine.py` |
| 179 | `api/services/confidence_scorer.py` |
| 200 | `api/services/edgar_adapter.py` |
| 782 | `api/services/financial_calc.py` |
| 155 | `api/services/graph_rag_engine.py` |
| 28 | `api/services/guardrails/__init__.py` |
| 262 | `api/services/guardrails/consensus_rails.py` |
| 213 | `api/services/guardrails/dialog_rails.py` |
| 172 | `api/services/guardrails/execution_rails.py` |
| 172 | `api/services/guardrails/input_rails.py` |
| 173 | `api/services/guardrails/output_rails.py` |
| 236 | `api/services/guardrails/persona_rails.py` |
| 109 | `api/services/guardrails/retrieval_rails.py` |
| 2289 | `api/services/langgraph_engine.py` |
| 78 | `api/services/llm_health.py` |
| 203 | `api/services/metric_router.py` |
| 730 | `api/services/peer_comparison.py` |
| 204 | `api/services/polygon_verifier.py` |
| 249 | `api/services/runtime_snapshot.py` |
| 100 | `api/services/schema_validator.py` |
| 222 | `api/services/sec_analyzer.py` |
| 106 | `api/services/sec_client.py` |
| 151 | `api/services/semantic_validator.py` |
| 140 | `api/services/shadow_runner.py` |
| 457 | `api/services/structure_chunker.py` |
| 65 | `api/services/verification.py` |
| 87 | `api/services/verifier.py` |
| 109 | `api/services/xbrl_client.py` |
| 119 | `api/services/xbrl_cross_validator.py` |
| 4 | `api/services/xbrl_mapper.py` |
| 4 | `api/services/xbrl_parser.py` |
| 451 | `api/services/xbrl_relevance.py` |
| 4 | `api/services/xbrl_validator.py` |

`api/models/` and `api/services/guardrails/` were deleted whole (both are
unreachable packages with no live submodules). `api/services/__init__.py` was
**kept**: it is a package init with live submodules. Live survivors:
`api/services/{__init__,embeddings,exceptions,hybrid_retriever,reranker,sec_knowledge_graph,sentiment}.py`.

`api/config.py` lost `DB_PATH`, `REVIEW_DB_PATH`, `PERSIST_DIR` handling and
`_validate_db_path()` (lines 7–71 of the old file). No live module read those
properties; the only readers were `runtime_snapshot.py` (deleted) and
`langgraph_engine.py` (deleted). Proven before deletion:

```text
$ git grep -n -E 'config\.(DB_PATH|REVIEW_DB_PATH)'
api/services/runtime_snapshot.py:212:    db_path = config.REVIEW_DB_PATH
```

### 1b. Deleted tests (12 files, 3,759 lines)

Only tests whose subject was a deleted module; nothing covering live code was
removed:

| lines | file |
| ---: | --- |
| 98 | `tests/rag/test_chat_engine.py` |
| 159 | `tests/rag/test_edgar_adapter.py` |
| 398 | `tests/rag/test_eval_pipeline.py` |
| 167 | `tests/rag/test_eval_types.py` |
| 219 | `tests/rag/test_financial_calc.py` |
| 91 | `tests/rag/test_graph_rag_engine.py` |
| 163 | `tests/rag/test_guardrails.py` |
| 449 | `tests/rag/test_langgraph_engine.py` |
| 164 | `tests/rag/test_peer_comparison.py` |
| 162 | `tests/rag/test_persona_rails.py` |
| 114 | `tests/rag/test_verifier.py` |
| 253 | `tests/rag/test_xbrl_relevance.py` |

Two mixed files kept their live cases and lost only the dead ones:

- `tests/rag/test_sec_rag_ingest.py`: deleted `TestXbrlClientUserAgent`
  (2 tests) — it imported `api.services.xbrl_client`, which no longer exists.
  All `pipelines/sec_rag_ingest.py` coverage stays.
- `tests/rag/conftest.py`: removed the `_stub_xbrl_client` and
  `_no_cross_encoder_load` autouse fixtures plus their helpers (they imported
  `api.services.xbrl_client` / `api.services.verifier`), and the now-unused
  `langgraph` entries in `problematic_modules`. The network guard, embedding
  fake, retriever reset and spark guards are unchanged. `test_guard_mutation_proofs.py`'s
  anchors (`socket.connect` patch, `_extract_host_port`) are untouched, so its
  subprocess proof still works.

`git diff --cached --stat` on the code commit: **60 files changed, 387
insertions(+), 12,125 deletions(-)**.

## 2. New guard: `tests/test_no_dead_api_modules.py`

- `scripts/check_api_reachability.py` is the derived engine. It builds the
  import graph with `ast` over all production `.py` files (excluding `tests/`
  and any `archive` directory), resolves relative imports, follows string
  references such as uvicorn targets, and BFS-walks from live entry points:
  `api.main`, every module under `agent/ pipelines/ gold/ silver/ etl/ bronze/
  ml/ strategies/ scripts/ notebooks/ (archive excluded) sec_kg/ analytics_nl/
  config/ evals/`, and every `.py` named in `resources/*.yml`.
- `unreachable_api_modules(root)` returns every `api.*` module not reachable
  from those roots, exempting package `__init__` modules that have at least one
  reachable submodule.
- **Nothing is hard-coded:** the inventory is re-derived on every test run. The
  test only asserts that the derived dead list is empty and includes
  non-vacuity checks (inventory ≥ 10, `api.main`/`api.deps`/
  `api.services.hybrid_retriever` reachable, every present entry package
  contributes nodes) plus synthetic-tree unit tests that prove both directions
  (dead module flagged; live package init exempt; an orphan package flagged;
  a module imported only by `tests/` flagged).

CLI: `python3 -I scripts/check_api_reachability.py <root>` → exit 1 when dead
modules exist.

## 3. Acceptance (CI parity)

Exact CI command: `pytest -q -m "not spark and not lakebase and not databricks"`
(`.github/workflows/ci.yml:55`).

### Baseline, `origin/main` (`0dc5b1c`, before any change)

```text
RUN A (normal):  1 failed, 2942 passed, 64 skipped, 24 deselected in 363.65s
                 FAILED tests/rag/test_zz_isolation.py::test_databricks_connect_not_polluted
RUN B (pyspark blocked): 2933 passed, 74 skipped, 24 deselected in 329.03s (exit 0)
```

The single RUN A failure is environment-specific (pyspark 4.4.0.dev0 is
installed on this machine; CI has none) and pre-exists this PR.

### HEAD (`fb713ed`, identical tree to the run)

```text
RUN A (normal):  1 failed, 2768 passed, 46 skipped, 24 deselected in 306.85s
                 FAILED tests/rag/test_zz_isolation.py::test_databricks_connect_not_polluted   <- same pre-existing failure
RUN B (pyspark blocked via /tmp stub first on PYTHONPATH):
                 2759 passed, 56 skipped, 24 deselected in 335.95s (exit 0)
```

The pyspark stub was a package at `/tmp/rmrag-stub-ci/pyspark/__init__.py`
(outside the repo) containing only
`raise ModuleNotFoundError("No module named 'pyspark'")`; `PYTHONPATH=$STUB
python3 -c "import pyspark"` → `ModuleNotFoundError: No module named 'pyspark'`.
RUN B — the CI-shaped run without pyspark — is fully green.

Failure-for-failure comparison on the same focused subset
(`tests/rag tests/api tests/test_no_retired_sources.py
tests/test_requirements_completeness.py`), pyspark blocked, HEAD vs an
`origin/main` archive: the HEAD failure set is a **subset** of the baseline set
— 17 failed + 33 errors on both, and the single difference is the flaky
`tests/api/test_public_demo_security.py::test_different_leftmost_ips_get_separate_buckets`
which fails on the baseline run and passes here. No new failure was introduced.

Other commands:

```text
$ python3 -c "import api.main; import agent"                       -> OK
$ python3 -c "import api.services.hybrid_retriever, api.services.embeddings,
              api.services.sentiment, api.services.reranker,
              api.services.sec_knowledge_graph, api.services.exceptions"  -> OK
$ python3 -I scripts/check_api_reachability.py .
  api modules: 25 | reachable: 25 | unreachable: 0
$ byte-compile of the 8 task modules named in resources/*.yml      -> 8 compiled, 0 failures
```

## 4. Route table diff (origin/main vs HEAD, `git archive` copies)

Both trees were exported with `git archive` and dumped through
`fastapi.testclient.TestClient(app)` (FastAPI ≥0.140 keeps included routers
lazily, so the dump combines `app.openapi()["paths"]` with the concrete
non-API routes on `app.routes`):

```text
base entries=23 head entries=23
ROUTES IDENTICAL
GET  /                            GET  /api/analytics
GET  /api/health                  GET  /api/health/trace
GET  /api/market/{symbol}         GET  /api/notes
GET  /api/portfolio               GET  /api/sec/coverage
GET  /api/signals                 GET  /api/watchlists
GET  /docs                        GET  /docs/oauth2-redirect
GET  /openapi.json                GET  /redoc
HEAD /docs                        HEAD /docs/oauth2-redirect
HEAD /openapi.json                HEAD /redoc
POST /api/agent/chat              POST /api/orders/intents
POST /api/orders/{order_id}/approve  POST /api/orders/{order_id}/cancel
POST /api/watchlists
```

No route was added, removed or renamed.

## 5. Mutation proofs (isolated `/tmp` `git archive` copies)

**(b) The new test fails on the old behavior** — `origin/main` archive
(`/tmp/rmrag-r23-base`) plus the new test and helper:

```text
api modules: 65 | reachable: 25 | unreachable: 40
FAILED tests/test_no_dead_api_modules.py::test_every_api_module_is_reachable_from_a_live_entry_point
1 failed, 3 passed
```

The 40 derived names (matches §1a exactly):

```text
api.models, api.models.eval_types, api.models.review_schemas, api.models.schemas,
api.services._edgar_identity, api.services.calibration, api.services.chart_tool,
api.services.chat_engine, api.services.confidence_scorer, api.services.edgar_adapter,
api.services.financial_calc, api.services.graph_rag_engine, api.services.guardrails,
api.services.guardrails.{consensus_rails,dialog_rails,execution_rails,input_rails,
output_rails,persona_rails,retrieval_rails}, api.services.langgraph_engine,
api.services.llm_health, api.services.metric_router, api.services.peer_comparison,
api.services.polygon_verifier, api.services.runtime_snapshot, api.services.schema_validator,
api.services.sec_analyzer, api.services.sec_client, api.services.semantic_validator,
api.services.shadow_runner, api.services.structure_chunker, api.services.verification,
api.services.verifier, api.services.xbrl_client, api.services.xbrl_cross_validator,
api.services.xbrl_mapper, api.services.xbrl_parser, api.services.xbrl_relevance,
api.services.xbrl_validator
```

**(a) Re-adding one deleted module unimported makes the test fail** — HEAD
archive, `cp api/services/structure_chunker.py` back (nothing imports it):

```text
E       Left contains one more item: 'api.services.structure_chunker'
FAILED tests/test_no_dead_api_modules.py::test_every_api_module_is_reachable_from_a_live_entry_point
1 failed, 3 passed
```

Removing the copied file again → `4 passed`, so the proof is not an artefact of
the copy.

**Old-behavior existence proof** (`test -f`):

```text
api/services/langgraph_engine.py       base=yes head=no
api/services/runtime_snapshot.py       base=yes head=no
api/services/chat_engine.py            base=yes head=no
api/models/schemas.py                  base=yes head=no
api/services/guardrails/input_rails.py base=yes head=no
```

## 6. Docs / config text

- `docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md`: the gap-audit table
  no longer claims any deleted file exists here — every `api/services/<name>.py`
  path and the two "exists as legacy code" phrases are gone, replaced by the
  supported qp1 surface plus "the legacy service was deleted"; a status note
  above the table records the deletion and commit. The `Rag_workbench item`
  column keeps the *external* Rag_workbench service names the audit was about
  (that repository still owns them); it no longer asserts anything about this
  repository. The `review_queue.duckdb` mention in the B10 mutation list is now
  "read the retired review database directly".
- `api/services/sentiment.py`: docstring no longer points at
  `langgraph_engine.py`.
- `pipelines/sec_rag_ingest.py`: comment no longer claims the rate limiter is
  shared with `xbrl_client`.
- Retired strings are gone from tracked files outside `docs/archive` and
  `notebooks/archive`:

```text
$ git grep -n -E 'rag\.duckdb|review_queue\.duckdb|PERSIST_DIR|RUNTIME_SNAPSHOT_|APP_DATA_HF_TOKEN|egoh33/app_data' \
    -- . ':(exclude)docs/archive' ':(exclude)notebooks/archive'
(no output)
```

**Deliberately untouched (documented, not an oversight):**

- `docs/archive/**` and `notebooks/archive/**` — excluded by the request.
- `requirements*.txt` — excluded by the request (PR #71 generates it).
- `.agents/evidence/BUILD-evidently-drift-cleanup.md` — a historical build
  record that names `api.services.langgraph_engine` and
  `api/models/review_schemas` as the state at the time of that earlier PR.
  Rewriting a past evidence artifact would falsify the record; it is not
  docs/config describing the current tree. Say the word if the coordinator
  wants those historical mentions scrubbed too.

## 7. Runtime dependencies with no remaining import (requirements NOT edited)

Census: AST scan of every tracked `.py` outside `tests/` and `archive` after
the deletions, cross-checked with `git grep -w` (whole tree) and with
`git grep` against `origin/main` to prove *this PR* is what removed the last
importer.

| distribution | import | remaining importer after PR | proof |
| --- | --- | --- | --- |
| `duckdb>=0.10.0` | `duckdb` | **none** | `git grep -n -E '^from duckdb\|^import duckdb'` outside tests/archives → empty. Only `tests/analytics_nl/test_ddl.py` imports it (test-only); `runtime_snapshot.py:151,171` was the only `api/` import. |
| `pytz>=2023.3` | `pytz` | **none** | `git grep -l -w pytz` → `requirements.txt` + `tests/test_no_retired_sources.py` comments only; zero imports anywhere. It existed for duckdb's tz-aware client (`requirements.txt:28-32`). |
| `langgraph>=0.0.20` | `langgraph` | **none** | on `origin/main` only `graph_rag_engine.py:5` and `langgraph_engine.py:13` (both deleted). Now only `requirements.txt:23` and test name-mapping tables. |
| `edgartools>=2.0.0` | `edgar` | **none** | on `origin/main` only `_edgar_identity.py:16`, `edgar_adapter.py:144`, `sec_client.py:7` (all deleted). Remaining `edgar` hits are SEC URL strings (`/Archives/edgar/data/...`), not imports. |
| `polars>=0.20.0` | `polars` | **none** | on `origin/main` only `financial_calc.py:25`, `langgraph_engine.py:11,1716`, `peer_comparison.py:489`, `sec_client.py:6` (all deleted). `^import polars` outside tests → empty. |
| `tenacity>=8.2.0` | `tenacity` | **none** | on `origin/main` only `edgar_adapter.py:20` (deleted). `git grep -w tenacity` → `requirements.txt:16` only. |
| `langsmith>=0.8.18` | `langsmith` | **none** | on `origin/main` only `chat_engine.py:5` (`from langsmith import traceable`, deleted). `api/config.py` keeps the `LANGSMITH_*` env-var settings only — no package import. |
| `langchain-openai>=0.1.0` | `langchain_openai` | **none** | on `origin/main` only `graph_rag_engine.py:6` (deleted). Remaining hits are test name-mapping tables. |

Still live (do **not** remove): `langchain-core` (`hybrid_retriever.py:36`,
`reranker.py:16`, `evals/rag_eval/*`), `rank-bm25` (`hybrid_retriever.py:38`,
`evals/rag_eval/corpus.py:399`), `huggingface-hub` (`embeddings.py:101`),
`sentence-transformers`, `openai` (`sentiment.py`, lazy), `numpy`, `pandas`,
`pydantic`, `fastapi`, `databricks-sdk`, `psycopg(-pool)`, `loguru`,
`python-dotenv`, `pyyaml`, `requests`, `uvicorn`, `finvizfinance`.

`oauthlib` has no direct import before or after this PR; it is a deliberate
transitive pin for `databricks-sql-connector` with a documented accepted CVE
(`docs/SECURITY.md:26,50`, `security/pip-audit-ignore.txt`) — **not** a
deletion candidate. CI also installs `duckdb` explicitly for the analytics_nl
tests (`.github/workflows/ci.yml:52`), so dropping it from `requirements.txt`
would be a separate CI change.

## 8. Non-goals respected

- No push, no PR edit, no merge, no deploy, no shared table/model/signal write.
- `requirements*.txt`, `docs/archive/**`, `notebooks/archive/**` untouched.
- No live module was edited except the two prose comments above.
- No new runtime dependency; `scripts/check_api_reachability.py` is stdlib-only
  (`ast`, `pathlib`, `re`, `sys`).
