# VERDICT: test-collection — Codex

CHANGES_REQUESTED

Blocking finding:

- `tests/rag/test_persona_rails.py:2` skips the entire module because `api.routes.conjoint` was removed. However, most tests exercise the still-present `api.services.guardrails.persona_rails` implementation, imported at line 3. For example, lines 39–153 test `check_persona_fit` and `_has_financial_figure`, whose implementations remain at `api/services/guardrails/persona_rails.py:98` and `:173`. Only the route-specific tests at lines 9–34 require the removed module. The test file must be split or conditionally skip only those route-specific tests; the current module-level skip hides meaningful live coverage.

Additional lost coverage:

- `tests/test_extract_cot.py:6` skips the whole file for the removed DuckDB layer, including the pure `_to_int` test at lines 27–33. `_to_int` still exists at `etl/extract_cot.py:140`. That assertion should remain runnable independently of DuckDB.
- `tests/bronze/test_bronze_polygon_bars.py:12` similarly hides pure `_ms_to_iso` coverage at lines 67–75 while `_ms_to_iso` remains at `etl/extract_polygon.py:431`. The module currently cannot import because production `etl/extract_polygon.py:19` still imports removed `db.database`, but that does not justify dropping the helper coverage wholesale.
- `tests/test_extract_polygon_ticks.py:6` says the removed tick extractor was “consolidated into `etl.extract_polygon`,” but `etl/extract_polygon.py` contains no tick/list-trades implementation. The module is genuinely absent, but the stated reason is inaccurate and should say it was removed/not carried forward.

Skip audit:

| Tests | Classification | Verification |
|---|---|---|
| Bronze Polygon bars/options, yfinance bars/indices; silver index/OHLCV; extract COT/options/stocks | DuckDB skip | `db/database.py` is absent, but several corresponding ETL modules still exist. Whole-file skips hide at least the helper coverage identified above. |
| `tests/test_extract_polygon_ticks.py` | Removed module | `etl/extract_polygon_ticks.py` is absent; stated consolidation is unsupported. |
| `tests/test_security.py` | Removed modules | `rag_engine.py` and `query.py` are both absent; skip is justified. |
| `tests/rag/test_extract_graph_triples.py` | Removed module | `scripts/` and `scripts.extract_graph_triples` are absent; justified. |
| `tests/rag/test_eval_pipeline.py:293` | Targeted removed-module skip | `api/db/review_queue.py` is absent. The class-level reason clearly identifies the retired DuckDB component; justified. |
| `tests/rag/test_persona_rails.py` | Removed route, live service | `api/routes/conjoint.py` is absent, but the persona rail remains. Current whole-module skip is unjustified. |
| Chat, GraphRAG, LangGraph tests | Optional dependencies | Correctly use `pytest.importorskip("openai")`, `pytest.importorskip("langchain_openai")`, and `pytest.importorskip("edgar")`, so they run when installed. |

Diff integrity:

- No test files were deleted.
- No assertions were weakened or removed.
- No production code changed.
- `db/database.py` was not recreated.
- The only removed diff lines are import-order changes in three tests, not assertions.

Required command results:

- `python3 -m pytest --co -q` → `340 tests collected in 1.49s`, 0 collection errors.
- `python3 -m pytest -q -m 'not spark and not lakebase and not databricks'` → `12 failed, 272 passed, 56 skipped, 16 deselected in 3.62s`.

The 12-failure attribution is correct:

- All 12 failures are in `tests/rag/test_sentiment.py`.
- `data/sentiment_dict/lm_word_lists.json` is absent both from this branch and `origin/main`.
- `api/services/sentiment.py:28` expects that exact file, and lines 58–64 return empty frozen sets when it is missing.
- The failures consistently result from those empty sets: dictionary-size assertions at `tests/rag/test_sentiment.py:30–38`, expected-word assertions at `:55–65`, and downstream count assertions such as `:104–118`, `:156–165`, and `:206–207`.
- Git history shows the dictionary on other slice branches, but not on `origin/main`. Thus these failures are unrelated to this branch’s collection changes.

