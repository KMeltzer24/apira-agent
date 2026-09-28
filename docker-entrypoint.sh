#!/bin/sh
set -e

ROLE="${AGENT_ROLE:-supervisor}"
PORT="${PORT:-8100}"
export PORT

case "$ROLE" in
  supervisor)
    exec uvicorn server:app --host 0.0.0.0 --port "$PORT" --no-access-log
    ;;
  portfolio)
    exec python -m agents.portfolio_sub_agent.a2a_main
    ;;
  research)
    exec python -m agents.research_sub_agent.a2a_main
    ;;
  *)
    echo "Unknown AGENT_ROLE=$ROLE (expected supervisor, portfolio, or research)" >&2
    exit 1
    ;;
esac
