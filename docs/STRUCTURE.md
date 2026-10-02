# Repository structure

The repo is now an **application** with three runtime layers and three
supporting pipelines. One line per top-level directory:

## App runtime

- `api/` — FastAPI backend: `api/main.py` entrypoint, `api/deps.py` dependency
  providers (Lakebase, Delta reader, authenticated user + server-side roles),
  `api/routes/` (one module per resource), `api/schemas.py` (response
  contracts), and read-only inherited `api/services/` + `api/models/`.
- `frontend/` — React + TypeScript + Tailwind SPA (Vite). Eight rubric screens,
  a single typed API client, and shared components.
- `agent/` — agent orchestration, retrieval/write tool contracts, and
  deterministic risk guardrails.
- `execution/` — IBKR paper-trading execution bridge (interface only; no live
  broker connectivity).

## Data pipeline

- `etl/` — source extraction and bronze-layer ingestion clients.
- `silver/` — cleaned, conformed, and enriched transformation logic.
- `gold/` — curated analytical and serving-layer transforms (features, signals).
- `pipelines/` — end-to-end pipeline orchestration.
- `db/` — storage adapters and database access: Lakebase (Postgres) client,
  Delta adapter, and forward-only migrations.
- `ontology/` — semantic metadata, business terms, and join hints.

## Research

- `ml/` — model training, inference, and model-specific utilities.
- `strategies/` — trading strategy configuration and calculations.
- `evals/` — evaluation runners and metrics.
- `notebooks/` — active Databricks ingestion notebooks (with `archive/`).

## Support

- `config/` — project settings and ticker-universe configuration.
- `docs/` — architecture, deployment, migration, and evaluation planning.
- `tests/` — automated test suites mirroring production areas.
