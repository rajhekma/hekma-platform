#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

cmd="${1:-up}"

case "$cmd" in
  up)
    docker compose up -d
    echo ""
    echo "Platform stack is up."
    echo "  Gateway:    http://localhost:${GATEWAY_PORT:-9080}/health"
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
    docker compose down
    ;;
  logs)
    docker compose logs -f "${2:-}"
    ;;
  ps)
    docker compose ps
    ;;
  reset)
    docker compose down -v
    echo "Removed containers and volumes."
    ;;
  *)
    echo "Usage: $0 {up|down|logs|ps|reset}"
    exit 1
    ;;
esac
