#!/bin/sh
set -e

ROLE="${AGENT_ROLE:-supervisor}"
PORT="${PORT:-8100}"
export PORT

case "$ROLE" in
  supervisor)
    exec uvicorn server:app --host 0.0.0.0 --port "$PORT" --no-access-log
    ;;
  portfolio|research)
    exec python a2a_server.py
    ;;
  *)
    echo "Unknown AGENT_ROLE=$ROLE (expected supervisor, portfolio, or research)" >&2
    exit 1
    ;;
esac
