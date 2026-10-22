# syntax=docker/dockerfile:1
#
# deploy/hf/Dockerfile — public demo image for the Hugging Face Docker Space.
#
# Why this path and not a root Dockerfile: the Hub's Docker builder only looks
# for `Dockerfile` at the repository root, but a root Dockerfile in this repo
# would be auto-detected by unrelated tooling (and invite `docker build .`
# without the frontend stage). `scripts/publish_hf_space.sh` stages a clean
# `git archive` of the tracked tree and copies THIS file to `Dockerfile` at the
# staged root, so the Space builds exactly this recipe.
#
# Build locally (context = repo root):
#   docker build -f deploy/hf/Dockerfile -t qp1-demo .
#   docker run --rm -p 7860:7860 qp1-demo
#
# The image is a read-only public showcase: PUBLIC_DEMO=1 disables every write
# route and startup refuses to run with Lakebase/Databricks/broker credentials
# (see api/demo.py). No secrets are baked in.

# ── Stage 1: build the React SPA ─────────────────────────────────────────────
# Public PostHog values are inlined by Vite at build time (same public key as
# the retired render.yaml shipped; unset -> analytics stays disabled).
ARG VITE_POSTHOG_KEY=phc_wDkoGZMNcMGsT2K7i5JToaVeAVycRiCxzNoE9vUhXHFb
ARG VITE_POSTHOG_HOST=https://us.i.posthog.com

FROM node:20.18.0-slim AS frontend
ARG VITE_POSTHOG_KEY
ARG VITE_POSTHOG_HOST
ENV VITE_POSTHOG_KEY=${VITE_POSTHOG_KEY} \
    VITE_POSTHOG_HOST=${VITE_POSTHOG_HOST}
WORKDIR /build/frontend
# Dependency manifests first so `npm ci` is cached independently of sources.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build && test -f dist/index.html

# ── Stage 2: python runtime ──────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# uv is pinned (same version as the developer/CI toolchain) and copied from its
# official image rather than installed with pip.
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

# The `python:3.12-slim` base image records `ENV GPG_KEY=<CPython release-signing
# fingerprint>` and Docker carries that variable into this stage. `api/demo.py`
# rejects every non-empty `*_KEY` while PUBLIC_DEMO=1 (deliberately broad: a
# false positive is safer than a shipped credential), so the inherited value
# made the Space refuse to boot. Shadow it with an empty value: this stage never
# downloads or verifies a CPython source tarball — the interpreter is the one
# from the base image. Covered by tests/deploy/test_hf_image_env_boots.py.
ENV GPG_KEY= \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface

# `python:3.12-slim` may ship a reduced zoneinfo tree; api imports
# `agent.guardrails`, which resolves America/New_York at module import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user

WORKDIR /home/user/app

# Runtime-only install from the committed lock (no dev group, no project build:
# pyproject sets `package = false`).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Only the packages the demo imports, plus the built SPA.
COPY --chown=user api ./api
COPY --chown=user agent ./agent
COPY --chown=user db ./db
COPY --chown=user config ./config
COPY --chown=user security ./security
COPY --chown=user pipelines ./pipelines
COPY --chown=user sec_kg ./sec_kg
COPY --chown=user data/sentiment_dict ./data/sentiment_dict
COPY --chown=user --from=frontend /build/frontend/dist ./frontend/dist

ENV PATH="/home/user/app/.venv/bin:${PATH}" \
    HOME=/home/user \
    PUBLIC_DEMO=1 \
    APP_ENV=demo

USER user

# HF Spaces route the public URL to this port (README `app_port: 7860`).
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3).status == 200 else 1)"]

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers"]
