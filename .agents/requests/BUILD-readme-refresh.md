# BUILD: README refresh (MiMo)

Rewrite `README.md` (repo root) so it accurately describes the platform as it is on `main`, plus the
work in flight. It is stale today: `services/` and `app.py` moved to `api/services/` and `api/main.py`,
it claims "Vector Search" (not used), and it omits most of the current system. **Every claim must be
true of the repo.** Verify each path you mention exists (`ls` / `git ls-files`). Where something is not
on main yet, label it **"in review (PR #N)"**. Never present a result more favourably than the fact
sheet does.

## Fact sheet (from Claude; verified live)
- **Purpose:** a mid-frequency (daily) quant research and paper-trading platform on Databricks:
  - a medallion lakehouse;
  - point-in-time (PIT) safe features;
  - a residual mean-reversion strategy with honest evaluation;
  - an SEC-filing RAG agent tool;
  - a FastAPI + React app;
  - Lakebase (Postgres) for app state and approvals.

  Unity Catalog: `bootcamp_students.evangoh_capstone`. SQL warehouse `b15d3d6f837ba428`.
- **Data (bronze, incremental append-only refresh notebooks `notebooks/refresh_bronze_{equities,options,cot,fed}.py`, PR #17 merged):**

  | Table | Rows | Coverage |
  |---|---:|---|
  | `bronze_ohlcv` (minute) | 73.3M | to 2026-10-01 |
  | `bronze_ohlcv_day` | — | 20,412 symbols |
  | `bronze_options_day` | 152.1M | 7,833 underlyings |
  | COT tables | — | to 2026-09-22 |
  | `bronze_fed_series` | 96,992 | — |

  - Sources: Massive S3 flat files (equities and options), CFTC, FRED.
  - PIT convention: every row has `information_available_ts`. Daily bars become available at
    16:00 NY + 30 min. FRED market rates use the H.15 publication calendar.
- **Silver/Gold (PR #8):**
  - `gold_tradable_universe`: top-300 by 60-session median dollar volume, PIT. Full-window, recency
    5, ≥252 own sessions.
  - `gold_regime_features`: RSP/SPY breadth regime BROAD/MIXED/NARROW, full-window guards.
  - Runner: `pipelines/run_silver_gold.py`.
- **Strategy:**
  - Residual mean-reversion (`strategies/`, PR #16 in review).
  - Latest live results r7: net Sharpe −0.382, OOS −0.636, deflated Sharpe 0.000; NARROW-gated
    +0.251 in-sample (−0.278 at 2× costs). **No demonstrated edge.** The report says so.
  - Robustness suite and PCA factor model: branch `slice/strategy-robustness`, in review.
- **ML (PR #9):** purged/embargoed walk-forward CV, triple-barrier labels, uniqueness weighting
  (`ml/`).
- **RAG (PR #18 merged, #19 in review):** `agent/tools_retrieval.py::search_sec_filings(symbol,
  query, as_of, top_k)`.
  - Retrieval: bge-small 384-d + BM25, RRF k=60, cross-encoder rerank.
  - PIT filter before scoring. Config errors return `reason: embedding_config`; a transient embedder
    failure falls back to BM25-only.
  - Coverage today: 16 semiconductor tickers, 10,720 chunks. Expansion to the 300/557-name universe
    is in progress, as is the eval framework (golden set + retrieval metrics + PIT-leakage gate).
- **App:** FastAPI `api/main.py` + React/Vite `frontend/`, deployed as a Databricks App (`app.yaml`).
  - Lakebase approvals: viewer default, trader role granted out of band (`scripts/grant_approver.py`).
  - Public Render demo (read-only `PUBLIC_DEMO` mode, no credentials, snapshot data): plan in
    `docs/RENDER_DEPLOY_PLAN.md`; PRs #20 and lane B in review. **Not deployed.**
- **Streaming:** `bundles/streaming/` continuous DLT bundle (PR #15). Built, **not deployed or run**.
- **CI/CD (PR #14):** GitHub Actions (tests, frontend build, secret scan, bundle validate), manual CD,
  Databricks Asset Bundle `databricks.yml`. CodeRabbit reviews are triggered by commenting
  `@coderabbitai review`.
- **Engineering process** (one short section): multi-agent build and review. MiMo builds, DeepSeek
  checks, Codex reviews, Claude reviews last and runs live checks, then the PR and CodeRabbit.
  Protocol in `.agents/PROTOCOL.md`.

## Required sections
1. Title and a one-paragraph summary.
2. A status table: component | state (merged / in review / not deployed) | PR.
3. An architecture diagram as ASCII or Mermaid, kept accurate: sources → bronze → silver/gold →
   strategy/ML, and → RAG → agent → API → frontend; Lakebase for app state.
4. A repository layout table, generated from the real top-level directories.
5. Quick start:
   - local tests: `python -m pytest -q --ignore=tests/lakebase`;
   - the frontend build;
   - running the app locally with `APP_ENV=dev`;
   - Databricks Connect serverless notes (mutually exclusive with pyspark).
6. Key results, with the honest strategy numbers above and links to the results files that exist on
   main.
7. A data and point-in-time conventions summary.
8. Links to the docs in `docs/`, only ones that exist.
9. Known limitations: no edge; RAG covers 16 tickers today; Lakebase is stopped by default; the
   Polygon REST key is invalid; streaming not deployed; the Render demo not deployed.

Keep it under about 300 lines. No secrets, no hostnames beyond what's already public in the repo.
LF line endings. Don't touch `.agents/dispatch.sh`. Commit with a descriptive message. Write
`.agents/mimo/VERDICT-readme-refresh.md` listing every path you referenced and how you verified it
exists.
