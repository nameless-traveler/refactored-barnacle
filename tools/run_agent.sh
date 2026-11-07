#!/usr/bin/env bash
set -euo pipefail

PROMPT_FILE="${1:?usage: run_agent.sh <prompt-file>}"
TIMEOUT="${AGENT_TIMEOUT_SEC:-5400}"

BIN="$(command -v kilo || true)"
if [ -z "$BIN" ]; then
  echo "no 'kilo' binary found (npm install -g @kilocode/cli)" >&2
  exit 1
fi

echo "using $("$BIN" --version 2>&1 | head -1)"
echo "--- nemotron models visible to this CLI ---"
"$BIN" models 2>&1 | grep -i nemotron || echo "(none listed)"
echo "-------------------------------------------"

MODEL_ARGS=()
if [ -n "${AGENT_MODEL:-}" ]; then MODEL_ARGS=(-m "$AGENT_MODEL"); fi

timeout "$TIMEOUT" "$BIN" run --auto "${MODEL_ARGS[@]}" "$(cat "$PROMPT_FILE")"
