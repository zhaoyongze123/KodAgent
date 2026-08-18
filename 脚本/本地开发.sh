#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/脚本/.local-dev.env"
FRONTEND_DIR="$ROOT_DIR/yudao-ui/yudao-ui-admin-vben-temp/apps/web-antd"
BACKEND_PORT=7800
FRONTEND_PORT=7700
BACKEND_LOG="${TMPDIR:-/tmp}/ruoyi-backend.log"
FRONTEND_LOG="${TMPDIR:-/tmp}/ruoyi-frontend.log"

load_env() {
  if [[ ! -r "$ENV_FILE" ]]; then
    echo "Missing $ENV_FILE. Copy 脚本/.local-dev.env.example and fill in local service credentials." >&2
    exit 1
  fi

  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a

  : "${MASTER_DATASOURCE_URL:?MASTER_DATASOURCE_URL is required}"
  : "${MASTER_DATASOURCE_USERNAME:?MASTER_DATASOURCE_USERNAME is required}"
  : "${MASTER_DATASOURCE_PASSWORD:?MASTER_DATASOURCE_PASSWORD is required}"
  : "${REDIS_HOST:?REDIS_HOST is required}"
  : "${REDIS_APP_PORT:?REDIS_APP_PORT is required}"
  : "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
  [[ "${SERVER_PORT:-$BACKEND_PORT}" == "$BACKEND_PORT" ]] || {
    echo "SERVER_PORT must be $BACKEND_PORT for local development." >&2
    exit 1
  }
}

stop_port() {
  local port="$1"
  local pid
  pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$pid" ]] && return 0

  kill "$pid"
  for _ in {1..20}; do
    sleep 0.5
    lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || return 0
  done
  echo "Port $port did not stop gracefully." >&2
  return 1
}

start_backend() {
  load_env
  stop_port "$BACKEND_PORT"
  (
    cd "$ROOT_DIR"
    # spring-boot:run resolves sibling modules from ~/.m2, so install the
    # current reactor first to avoid running stale snapshot dependencies.
    mvn -pl yudao-server -am install -DskipTests
    exec mvn -pl yudao-server spring-boot:run \
      -Dspring-boot.run.profiles="$SPRING_PROFILES_ACTIVE" \
      -Dspring-boot.run.arguments="--server.address=$SERVER_ADDRESS --server.port=$SERVER_PORT"
  )
  echo "Backend starting with Maven: http://127.0.0.1:$BACKEND_PORT"
}

start_frontend() {
  if [[ -r "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
  stop_port "$FRONTEND_PORT"
  (
    cd "$FRONTEND_DIR"
    VITE_GLOB_FILE_PREVIEW_URL="${OA_FILE_PREVIEW_URL:-}" \
    VITE_GLOB_FILE_PREVIEW_FETCH_ORIGIN="${OA_FILE_PREVIEW_FETCH_ORIGIN:-}" \
      nohup pnpm dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
  )
  echo "Frontend starting: http://127.0.0.1:$FRONTEND_PORT (log: $FRONTEND_LOG)"
}

case "${1:-}" in
  backend) start_backend ;;
  frontend) start_frontend ;;
  all) start_backend; start_frontend ;;
  stop) stop_port "$FRONTEND_PORT"; stop_port "$BACKEND_PORT" ;;
  *)
    echo "Usage: bash 脚本/本地开发.sh {backend|frontend|all|stop}" >&2
    exit 1
    ;;
esac
