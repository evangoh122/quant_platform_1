---
title: Quant Platform — public demo
emoji: 📈
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Read-only quant research demo — snapshots, no credentials
---

# Quant Platform — public demo

Read-only showcase of the Quant Platform: point-in-time market features,
SEC research retrieval, trading signals and analytics served by a FastAPI app
with a React SPA.

This Space is **generated** — do not edit files here by hand. The source of
truth is the main repository; publish with `scripts/publish_hf_space.sh`
(dry-run by default, `--yes` required) from a clean checkout at `origin/main`.
Deployment notes live in `docs/HF_SPACE_DEPLOY.md`.

Runtime guarantees:

- `PUBLIC_DEMO=1` and `APP_ENV=demo`: anonymous, read-only, no write routes.
- The container holds **no credentials** — no Lakebase, Databricks or broker
  tokens. Startup fails closed if any appear (see `api/demo.py`).
- Served on port 7860; health endpoint at `/api/health`.
