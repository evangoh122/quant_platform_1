# Repository structure

- `agent/` — agent orchestration, guardrails, and tool integrations.
- `api/` — backend routes, domain services, and API data models.
- `config/` — project settings and ticker-universe configuration.
- `db/` — storage adapters and database access.
- `docs/` — architecture, migration, repository, and evaluation planning documents.
- `etl/` — source extraction and bronze-layer ingestion clients.
- `evals/` — evaluation runners and metrics.
- `execution/` — execution-system integration and bridges.
- `gold/` — curated analytical and serving-layer transforms.
- `ml/` — model training, inference, and model-specific utilities.
- `ontology/` — semantic metadata, business terms, and join hints.
- `pipelines/` — end-to-end pipeline orchestration.
- `silver/` — cleaned, conformed, and enriched transformation logic.
- `strategies/` — trading strategy configuration and calculations.
- `tests/` — automated test suites mirroring production areas.
- `notebooks/` — active Databricks ingestion notebooks.
  - `archive/` — archived one-time setup notebooks.
