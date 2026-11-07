#!/usr/bin/env bash
# The ONLY seam between the harness and the agent. To plug in your own agent, replace the last line.
# Contract: read the prompt from the file given as $1, work in the current directory (the repo),
# exit 0 when finished. The harness does not trust the agent's own claim of success: tools/verify.py
# runs afterwards in a separate job that has no API key.
set -euo pipefail

PROMPT_FILE="${1:?usage: run_agent.sh <prompt-file>}"
TIMEOUT="${AGENT_TIMEOUT_SEC:-5400}"   # 90 minutes per issue by default

BIN="$(command -v kilo || command -v kilocode || true)"
if [ -z "$BIN" ]; then
  echo "no kilo/kilocode binary found; install it or replace this script" >&2
  exit 1
fi

# --auto = non-interactive autonomous mode, --timeout is in seconds (per the Kilo CLI docs).
# NOT VERIFIED: how this CLI is told which provider/model to use headlessly. Test that first (README.md).
timeout "$((TIMEOUT + 60))" "$BIN" --auto --timeout "$TIMEOUT" < "$PROMPT_FILE"
