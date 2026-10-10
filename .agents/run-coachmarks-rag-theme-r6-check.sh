#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.nvm/versions/node/v26.5.0/bin:$PATH"
cd /home/jianj/code/qp1-rag-theme
for b in node npm npx; do p=$(command -v $b); case "$p" in /mnt/*|"") echo "boundary: $b resolves to $p" >&2; exit 3;; esac; done
node -p "process.platform" | grep -qx linux
SHA=$(git rev-parse HEAD)
echo "HEAD SHA: $SHA"
test -z "$(git status --porcelain --untracked-files=no)"
git merge-base --is-ancestor origin/main HEAD
git diff --check origin/main...HEAD
cd frontend
npx tsc --noEmit
npx vitest run
npm run build
echo "--- legacy emerald/red residuals (non-test tsx) ---"
grep -rEn 'bg-emerald-|bg-red-|text-emerald-|text-red-' src --include=*.tsx | grep -v '\.test\.' || echo none
echo "--- legacy bg-black/58 residuals (non-test tsx) ---"
grep -rEn 'bg-black/58' src --include=*.tsx | grep -v '\.test\.' || echo none
echo "r6 check script finished"