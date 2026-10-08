#!/usr/bin/env bash
# Dispatch an implementation request to MiMo.
#
#   .agents/dispatch.sh <agent> <request-file> [timeout-seconds]
#
# agent: mimo
# Writes combined output to .agentlogs/<agent>-<request>.log (gitignored)
# and returns the agent's exit code.

set -uo pipefail

AGENT="${1:?usage: dispatch.sh mimo <request-file> [timeout]}"
REQUEST="${2:?usage: dispatch.sh mimo <request-file> [timeout]}"
TIMEOUT="${3:-1800}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

[ -f "$REQUEST" ] || { echo "no such request file: $REQUEST" >&2; exit 2; }

mkdir -p .agentlogs
LOG=".agentlogs/${AGENT}-$(basename "$REQUEST" .md).log"

PROMPT="You are working in the git repository at $REPO.

Read and follow AGENTS.md, then execute the request in $REQUEST as the MiMo
implementation stage.

Work only inside $REPO. Do not push to main. Do not commit secrets.
When finished, write the requested evidence and emit the exact BUILD DONE line
specified by AGENTS.md."

echo "[dispatch] agent=$AGENT request=$REQUEST timeout=${TIMEOUT}s log=$LOG"

case "$AGENT" in
  mimo)
    timeout "$TIMEOUT" opencode run --auto -m xiaomi-token-plan-sgp/mimo-v2.5-pro \
      --title "qp1-$(basename "$REQUEST" .md)" "$PROMPT" 2>&1 | tee "$LOG"
    ;;
  *)
    echo "unknown agent: $AGENT (expected mimo)" >&2; exit 2 ;;
esac

RC=${PIPESTATUS[0]}
echo "[dispatch] agent=$AGENT exit=$RC"
exit "$RC"
