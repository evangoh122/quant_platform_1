===REPORT START===

Implemented round 6 in:

- [ontology files](/home/jianj/code/qp1-onto/ontology)
- [tests/test_ontology.py](/home/jianj/code/qp1-onto/tests/test_ontology.py)

Tables added or changed:

- `bronze_ohlcv_day` — marked unadjusted; verified against `origin/main:notebooks/refresh_bronze_equities.py:42-52` and `slice/nl-contracts:docs/NL1_PROPOSED_SERVING_VIEWS.md:12-15`.
- `bronze_cftc_com` — verified against `origin/main:notebooks/refresh_bronze_cot.py:55-65,465-486`.
- `bronze_corporate_actions` — verified against `slice/corporate-actions:notebooks/refresh_bronze_corporate_actions.py:40-53` and `etl/corporate_actions.py:23-36,69-83`. yfinance is implemented; Massive is marked planned.
- `silver_ohlcv_day_adjusted` and `data_quality_breaks` — verified against `slice/corporate-actions:silver/08_silver_ohlcv_day_adjusted.sql:24-73,123-187,195-257,315-403`.
- `sec_ingest_log` — verified against `slice/rag-coverage:pipelines/sec_rag_ingest.py:1256-1287`.
- `sec_cik_mapping_log` — verified writer and production wiring at `slice/rag-coverage:pipelines/sec_rag_ingest.py:1290-1311,1338-1361`.
- `gold_sec_coverage` — verified against `slice/rag-coverage:gold/07_gold_sec_coverage.sql:10-62`; the 300-current/557-ever universe comes from `.agents/requests/BUILD-rag-coverage.md:10`.
- `gold_sec_kg_build_runs` — verified against `slice/rag-kg:pipelines/build_sec_knowledge_graph.py:216-248`.
- Proposed views `serve_daily_prices_v1`, `serve_daily_equity_metrics_v1`, `serve_relative_performance_v1`, `serve_options_metrics_v1`, and `serve_bounded_daily_bars_v1` — registered as `status: proposed`; verified against `slice/nl-contracts:analytics_nl/data/semantic_registry_v1.yaml:9-14` and `docs/NL1_PROPOSED_SERVING_VIEWS.md:3-5,30-32,36-430`.

NL1 metrics added or updated:

- `price`, `return`, `volume`, `realized_volatility`, `drawdown`, `momentum`, `relative_performance`, `implied_volatility`, and `put_call_ratio`.
- Names verified at `slice/nl-contracts:analytics_nl/contracts.py:43-55`.
- Daily formulas and sources verified at `docs/NL1_PROPOSED_SERVING_VIEWS.md:9-21,36-338`.
- Options calculations additionally verified at `origin/main:gold/02_gold_options_features.sql:63-108`.
- Existing `return_N`, `rolling_realized_volatility`, and `momentum_N` are now explicitly flagged unadjusted, verified at `origin/main:gold/01_gold_ohlcv_features.sql:18-90`.
- Existing backtest drawdown was preserved as `backtest_equity_drawdown`, verified at `slice/ontology-update:ml/evaluate.py:167-169`.

Terms added:

- `split_adjusted_price` — `slice/corporate-actions:silver/08_silver_ohlcv_day_adjusted.sql:11-15,161-187`.
- `corporate_action` — `slice/corporate-actions:etl/corporate_actions.py:1-8,23-36`.
- `reverse_split` — `slice/corporate-actions:etl/corporate_actions.py:27-29`.

Other changes:

- Added daily-bars-to-adjusted-bars lineage.
- Added tests for local SQL target registration, all nine NL1 metrics, proposed-table/live-metric separation, and adjusted-versus-explicitly-unadjusted return metrics.
- Expanded table-reference resolution to include `adjusted_source_table`.
- KG enum snapshot was not changed: `slice/rag-kg:sec_kg/model.py:19-54` still matches it exactly.

Intentionally omitted:

- No Massive/yfinance precedence was claimed because the corporate-actions branch currently accepts only yfinance (`refresh_bronze_corporate_actions.py:43,70-84`).
- `split_source_mismatch` was not added because it does not exist on the branch.
- No columns or tables were guessed.

Validation:

- `python3 -m pytest tests/test_ontology.py -q` → **29 passed, 35 skipped**.
- YAML parse check → passed.
- `git diff --check` → passed.
- The requested `python` executable is unavailable; `/usr/bin/python3` was used.
- Full `python3 -m pytest -q --ignore=tests/lakebase` could not complete: verbose collection reached **898 tests / 13 collection skips**, then stalled at `tests/api/test_auth.py::test_no_auth_header_returns_401`. The isolated test reproducibly timed out after 30 seconds with exit 124. No full-suite pass count is claimed.

No push or commit was performed.

===REPORT END===
