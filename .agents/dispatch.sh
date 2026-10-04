#!/usr/bin/env bash
# Dispatch a build or review request to one of the coordinated agents.
#
#   .agents/dispatch.sh <agent> <request-file> [timeout-seconds]
#
# agent: deepseek | mimo | codex
# Writes combined output to .agentlogs/<agent>-<request>.log (gitignored)
# and returns the agent's exit code.

set -uo pipefail

AGENT="${1:?usage: dispatch.sh <deepseek|mimo|codex> <request-file> [timeout]}"
REQUEST="${2:?usage: dispatch.sh <deepseek|mimo|codex> <request-file> [timeout]}"
TIMEOUT="${3:-1800}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

[ -f "$REQUEST" ] || { echo "no such request file: $REQUEST" >&2; exit 2; }

mkdir -p .agentlogs
LOG=".agentlogs/${AGENT}-$(basename "$REQUEST" .md).log"

PROMPT="You are working in the git repository at $REPO.

Read and follow the protocol at .agents/PROTOCOL.md, then read your role at
.agents/${AGENT}/ROLE.md, then execute the request in $REQUEST.

Work only inside $REPO. Do not push to main. Do not commit secrets.
When finished, write your verdict file exactly as PROTOCOL.md specifies."

echo "[dispatch] agent=$AGENT request=$REQUEST timeout=${TIMEOUT}s log=$LOG"

case "$AGENT" in
  deepseek)
    timeout "$TIMEOUT" opencode run --auto -m deepseek/deepseek-v4-pro \
      --title "qp1-$(basename "$REQUEST" .md)" "$PROMPT" 2>&1 | tee "$LOG"
    ;;
  mimo)
    timeout "$TIMEOUT" opencode run --auto -m xiaomi-token-plan-sgp/mimo-v2.5-pro \
      --title "qp1-$(basename "$REQUEST" .md)" "$PROMPT" 2>&1 | tee "$LOG"
    ;;
  codex)
    timeout "$TIMEOUT" codex exec --full-auto "$PROMPT" 2>&1 | tee "$LOG"
    ;;
  *)
    echo "unknown agent: $AGENT (expected deepseek|mimo|codex)" >&2; exit 2 ;;
esac

RC=${PIPESTATUS[0]}
echo "[dispatch] agent=$AGENT exit=$RC"
exit "$RC"
