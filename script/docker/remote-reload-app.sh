#!/usr/bin/env bash
set -euo pipefail

REMOTE_DEPLOY_DIR="${REMOTE_DEPLOY_DIR:-/root/deployments/ruoyi-release}"
SERVER_TAR="${SERVER_TAR:-ruoyi-server-local.tar}"
ADMIN_TAR="${ADMIN_TAR:-ruoyi-admin-local.tar}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:48080/actuator/health}"
REMOTE_ENV_FILE="${REMOTE_ENV_FILE:-}"
DB_MIGRATION_FILE="${DB_MIGRATION_FILE:-/tmp/system-kod-sso-token-upgrade.sql}"
REMOTE_DB_CONTAINER="${REMOTE_DB_CONTAINER:-ruoyi-mysql}"

if [ -n "${REMOTE_ENV_FILE}" ] && [ -f "${REMOTE_ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${REMOTE_ENV_FILE}"
  set +a
fi

cd "${REMOTE_DEPLOY_DIR}"

if [ -z "${REMOTE_ENV_FILE}" ] && [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${MYSQL_DATABASE:=ruoyi-vue-pro}"
: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"

docker compose up -d mysql redis
for i in $(seq 1 60); do
  if docker exec "${REMOTE_DB_CONTAINER}" mysqladmin ping -uroot -p"${MYSQL_ROOT_PASSWORD}" --silent >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [ "${i}" -eq 60 ]; then
    echo "[错误] MySQL 在 120 秒内未就绪" >&2
    exit 1
  fi
done
if [ -f "${DB_MIGRATION_FILE}" ]; then
  docker exec -i "${REMOTE_DB_CONTAINER}" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" "${MYSQL_DATABASE}" < "${DB_MIGRATION_FILE}"
fi
docker compose stop server admin || true
docker compose rm -sf server admin || true

docker load -i "/tmp/${SERVER_TAR}"
docker load -i "/tmp/${ADMIN_TAR}"

docker compose up -d --no-build server admin

for i in $(seq 1 60); do
  if curl -fsS "${HEALTH_URL}" >/dev/null; then
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then
    echo "[错误] 后端健康检查未通过: ${HEALTH_URL}" >&2
    exit 1
  fi
done

rm -f "/tmp/${SERVER_TAR}" "/tmp/${ADMIN_TAR}" "${DB_MIGRATION_FILE}" "${REMOTE_ENV_FILE}"
docker image prune -f >/dev/null 2>&1 || true

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep 'ruoyi-'
curl -fsS "${HEALTH_URL}"
