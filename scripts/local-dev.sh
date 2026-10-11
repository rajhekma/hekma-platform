#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

cmd="${1:-up}"

run_ai_usage_nodocker() {
  local port="${COMMERCE_PORT:-8090}"
  local db_path="${ROOT}/hekma-ai-usage/data/commerce.db"
  mkdir -p "${ROOT}/hekma-ai-usage/data"

  echo "Docker is not installed on this machine."
  echo "Starting the AI Usage API in no-Docker mode (SQLite at ${db_path})."
  echo ""

  if curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    echo "Already running on http://127.0.0.1:${port}"
    echo "  curl http://127.0.0.1:${port}/health"
    echo "  curl http://127.0.0.1:${port}/v1/patients/203664/ai-cost"
    echo "Stop the existing process (the other terminal, or: lsof -ti tcp:${port} | xargs kill) before starting again."
    exit 0
  fi

  python3 -m pip install -q -r "${ROOT}/hekma-ai-usage/requirements.txt"

  export DATABASE_URL="sqlite:///${db_path}"
  export AI_USAGE_SQS_ENABLED=false
  export PYTHONPATH="${ROOT}/hekma-ai-usage/src:${ROOT}/shared${PYTHONPATH:+:$PYTHONPATH}"

  echo "AI Usage API: http://127.0.0.1:${port}/health"
  echo "Example:      curl http://127.0.0.1:${port}/v1/patients/203664/ai-cost"
  echo "Dashboard:    cd hekma-ai-usage/frontend && python3 server.py"
  echo "Stop with Ctrl+C"
  echo ""
  exec python3 -m uvicorn main:app --app-dir "${ROOT}/hekma-ai-usage/src" --host 127.0.0.1 --port "${port}"
}

case "$cmd" in
  up)
    if ! command -v docker >/dev/null 2>&1; then
      run_ai_usage_nodocker
    fi
    docker compose up -d
    echo ""
    echo "Platform stack is up."
    echo "  Gateway:    http://localhost:${GATEWAY_PORT:-9080}/health"
    echo "  AI Usage:   http://localhost:${COMMERCE_PORT:-8090}/health"
    echo "  Postgres:   localhost:${POSTGRES_PORT:-5433}"
    echo "  MySQL:      localhost:${MYSQL_PORT:-3307}"
    echo "  Redis:      localhost:${REDIS_PORT:-6379}"
    echo "  LocalStack: localhost:${LOCALSTACK_PORT:-4566}"
    echo ""
    echo "Start monoliths on the host, then hit the gateway:"
    echo "  Python (8000): hekma_data_pipleline"
    echo "  Java   (8080): hekma_api"
    ;;
  down)
    if ! command -v docker >/dev/null 2>&1; then
      echo "Docker is not installed; nothing to stop. Use Ctrl+C on the AI Usage API process."
      exit 0
    fi
    docker compose down
    ;;
  logs)
    if ! command -v docker >/dev/null 2>&1; then
      echo "Docker is not installed; logs print in the AI Usage API terminal."
      exit 0
    fi
    docker compose logs -f "${2:-}"
    ;;
  ps)
    if ! command -v docker >/dev/null 2>&1; then
      echo "Docker is not installed."
      exit 0
    fi
    docker compose ps
    ;;
  reset)
    if ! command -v docker >/dev/null 2>&1; then
      rm -f "${ROOT}/hekma-ai-usage/data/commerce.db"
      echo "Removed local SQLite database."
      exit 0
    fi
    docker compose down -v
    echo "Removed containers and volumes."
    ;;
  *)
    echo "Usage: $0 {up|down|logs|ps|reset}"
    exit 1
    ;;
esac
