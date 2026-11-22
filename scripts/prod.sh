#!/usr/bin/env bash
# Shortcut for the production stack:  ./scripts/prod.sh up -d --build | ps | logs -f backend | down
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env.prod ] || { echo "Missing .env.prod. Create it with: cp .env.prod.example .env.prod" >&2; exit 1; }
exec docker compose -f docker-compose.prod.yml --env-file .env.prod "$@"
