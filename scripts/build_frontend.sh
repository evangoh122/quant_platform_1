#!/usr/bin/env bash
# scripts/build_frontend.sh — Build the React frontend for deployment.
#
# Run this before `databricks bundle deploy` so that frontend/dist/ exists
# and the FastAPI backend can serve the SPA.
#
# Usage:
#   ./scripts/build_frontend.sh
#   # or from the repo root:
#   bash scripts/build_frontend.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

if [ ! -f "$FRONTEND_DIR/package.json" ]; then
  echo "ERROR: frontend/package.json not found at $FRONTEND_DIR" >&2
  exit 1
fi

echo "==> Installing frontend dependencies..."
cd "$FRONTEND_DIR"
npm ci

echo "==> Building frontend..."
npm run build

if [ ! -d "$FRONTEND_DIR/dist" ]; then
  echo "ERROR: frontend/dist/ was not produced by the build" >&2
  exit 1
fi

echo "==> Frontend built successfully → frontend/dist/"