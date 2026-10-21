#!/usr/bin/env bash
# scripts/build_frontend.sh — Build the React frontend.
#
# The PRIMARY path is now `databricks bundle deploy`: databricks.yml declares a
# `frontend` artifact whose build command is exactly the npm steps below, so no
# manual pre-build step is needed for a bundle deployment.
#
# This script remains as a thin wrapper for local builds, for the Hugging Face
# Docker image parity check, and for UI-driven app deployments:
#   ./scripts/build_frontend.sh

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

if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
  echo "ERROR: frontend/dist/index.html was not produced by the build" >&2
  exit 1
fi

echo "==> Frontend built successfully → frontend/dist/"