#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "Missing .env (copy .env.example to .env first)"; exit 1; }
[ -f data/sample_db/demo.sqlite ] || python -m data.seed

# Remote (streamable HTTP) server used by the agent
python -m servers.internal_tools_server.server --transport http --port 8080 &
HTTP_PID=$!
trap 'kill $HTTP_PID 2>/dev/null || true' EXIT
sleep 1

python -m agent.main "$@"