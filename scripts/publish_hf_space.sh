#!/usr/bin/env bash
# scripts/publish_hf_space.sh — Stage and publish the public demo to a
# Hugging Face Docker Space.
#
# The repo README.md is the project README, so the Space README comes from the
# template deploy/hf/README.space.md (HF needs `sdk: docker` YAML front matter).
# The Dockerfile lives at deploy/hf/Dockerfile and is copied to the staged root
# as `Dockerfile`, which is the only name the Hub's Docker builder looks for.
#
# Safety properties (AGENTS.md forbids deploying from an agent run):
#   * default is --dry-run: nothing leaves this machine;
#   * publishing requires an explicit --yes;
#   * refuses a dirty worktree or a HEAD that is not origin/main;
#   * stages `git archive` of tracked files into a temp dir OUTSIDE the repo;
#   * never accepts, prints, copies or writes the HF token — the Hub CLI reads
#     HF_TOKEN from the environment, or uses its existing `hf auth login`.
#
# Usage:
#   git fetch origin main
#   ./scripts/publish_hf_space.sh                # dry run (staged file list)
#   ./scripts/publish_hf_space.sh --dry-run --ref HEAD   # dry run off-main ref
#   ./scripts/publish_hf_space.sh --yes          # real upload (owner only)
#
# The Space id is a single placeholder constant; the owner sets HF_SPACE_REPO
# (or edits the constant) once the namespace/space name is decided.
set -euo pipefail

# The ONE place the space id lives. Placeholder until the owner decides.
# Override with HF_SPACE_REPO=<namespace>/<space> without editing the file.
HF_SPACE_REPO="${HF_SPACE_REPO:-<HF_NAMESPACE>/<HF_SPACE>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DRY_RUN=1
TARGET_REF="origin/main"

usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      DRY_RUN=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --ref)
      [[ $# -ge 2 ]] || fail "--ref needs a value"
      TARGET_REF="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --token|--token=*|--hf-token|--hf-token=*)
      fail "tokens are never accepted as arguments; export HF_TOKEN instead"
      ;;
    *)
      fail "unknown argument: $1 (see --help)"
      ;;
  esac
done

cd "$REPO_ROOT"

git rev-parse --git-dir >/dev/null 2>&1 || fail "not a git repository: $REPO_ROOT"

# ── cleanliness + ref checks (always applied) ───────────────────────────────
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Worktree is dirty:" >&2
  git status --short >&2
  fail "commit or stash changes first; the Space is staged from a clean tree"
fi

git rev-parse --verify --quiet "${TARGET_REF}^{commit}" >/dev/null \
  || fail "unknown ref '$TARGET_REF' (run: git fetch origin main)"

if [[ "$TARGET_REF" == "origin/main" ]]; then
  head_sha="$(git rev-parse HEAD)"
  main_sha="$(git rev-parse origin/main)"
  if [[ "$head_sha" != "$main_sha" ]]; then
    fail "HEAD ($head_sha) is not origin/main ($main_sha); merge first or use --dry-run --ref HEAD"
  fi
elif [[ "$DRY_RUN" -eq 0 ]]; then
  fail "--ref is only allowed with --dry-run; a real publish must be origin/main"
fi

# ── stage: tracked files only, outside the repo ─────────────────────────────
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/qp1-hf-space.XXXXXX")"
cleanup() { rm -rf "$STAGE_DIR"; }
trap cleanup EXIT

git archive --format=tar "$TARGET_REF" | tar -x -C "$STAGE_DIR"

git show "${TARGET_REF}:deploy/hf/README.space.md" > "$STAGE_DIR/README.md"
git show "${TARGET_REF}:deploy/hf/Dockerfile" > "$STAGE_DIR/Dockerfile"

# ── no secrets in the staged tree (defence in depth: git archive already
#    excludes untracked/gitignored files such as .env) ───────────────────────
# .env.example is the committed template: names only, no values (and the
# token-material grep below still scans it). Every other .env* file is refused.
secret_hits="$(find "$STAGE_DIR" \( -name '.env' -o -name '.env.*' \
  -o -name '*.pem' -o -name '*.key' -o -name 'auth.json' -o -name 'secrets.json' \) \
  ! -name '.env.example' -print)"
if [[ -n "$secret_hits" ]]; then
  echo "$secret_hits" >&2
  fail "secret-looking files present in the staged tree"
fi

if grep -rIlE '(hf_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' "$STAGE_DIR" >/dev/null; then
  grep -rIlE '(hf_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' "$STAGE_DIR" >&2
  fail "token/private-key material found in the staged tree"
fi

file_count="$(find "$STAGE_DIR" -type f | wc -l | tr -d ' ')"
echo "Staged $file_count tracked files from ${TARGET_REF} at $STAGE_DIR"
echo "Space target: $HF_SPACE_REPO"
echo "--- staged files ---"
( cd "$STAGE_DIR" && find . -type f | sort )

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "--- DRY RUN: nothing uploaded; pass --yes to publish ---"
  exit 0
fi

# ── real publish (owner only; never run from an agent session) ──────────────
case "$HF_SPACE_REPO" in
  *"<"*|*">"*)
    fail "HF_SPACE_REPO is still the placeholder '$HF_SPACE_REPO'; set the decided namespace/space"
    ;;
esac

command -v hf >/dev/null 2>&1 || fail "the 'hf' CLI is required (pip install huggingface_hub)"

# Auth: HF_TOKEN from the environment (read by the CLI, never printed) or an
# existing `hf auth login` session.
if [[ -z "${HF_TOKEN:-}" ]]; then
  hf auth whoami >/dev/null 2>&1 \
    || fail "not authenticated: export HF_TOKEN or run 'hf auth login'"
fi

echo "Uploading to $HF_SPACE_REPO ..."
hf upload "$HF_SPACE_REPO" "$STAGE_DIR" . \
  --repo-type space \
  --delete "*" \
  --commit-message "Publish public demo from $(git rev-parse --short HEAD)"

echo "Published OK"
