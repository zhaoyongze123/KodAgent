#!/usr/bin/env bash
set -euo pipefail

REMOTE_DEPLOY_DIR="${REMOTE_DEPLOY_DIR:-/home/daiwei/deployments/ruoyi-release}"
SERVER_TAR="${SERVER_TAR:-ruoyi-server-local.tar}"
ADMIN_TAR="${ADMIN_TAR:-ruoyi-admin-local.tar}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:48080/actuator/health}"
REMOTE_ENV_FILE="${REMOTE_ENV_FILE:-}"

if [ -n "${REMOTE_ENV_FILE}" ] && [ -f "${REMOTE_ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${REMOTE_ENV_FILE}"
  set +a
fi

cd "${REMOTE_DEPLOY_DIR}"

export AGENT_EVENT_SCHEMA_SQL_HOST_PATH="${AGENT_EVENT_SCHEMA_SQL_HOST_PATH:-./agent_run_event.sql}"
export AGENT_RUNTIME_SCHEMA_SQL_HOST_PATH="${AGENT_RUNTIME_SCHEMA_SQL_HOST_PATH:-./agent_runtime.sql}"
export AGENT_MODEL_SCHEMA_SQL_HOST_PATH="${AGENT_MODEL_SCHEMA_SQL_HOST_PATH:-./agent_model_config.sql}"
export AGENT_PARTY_KNOWLEDGE_SCHEMA_SQL_HOST_PATH="${AGENT_PARTY_KNOWLEDGE_SCHEMA_SQL_HOST_PATH:-./party_knowledge.sql}"
export AGENT_PARTY_KNOWLEDGE_VECTOR_SCHEMA_SQL_HOST_PATH="${AGENT_PARTY_KNOWLEDGE_VECTOR_SCHEMA_SQL_HOST_PATH:-./party_knowledge_vector.sql}"
export OA_PERSONAL_SCHEDULE_SCHEMA_SQL_HOST_PATH="${OA_PERSONAL_SCHEDULE_SCHEMA_SQL_HOST_PATH:-./system-personal-schedule-init.sql}"
export OA_PERSONAL_SCHEDULE_EFFECT_SCHEMA_SQL_HOST_PATH="${OA_PERSONAL_SCHEDULE_EFFECT_SCHEMA_SQL_HOST_PATH:-./agent_personal_schedule_effect.sql}"
export OA_PARTY_FILE_SCHEMA_SQL_HOST_PATH="${OA_PARTY_FILE_SCHEMA_SQL_HOST_PATH:-./party-file-kod-schema-v2.sql}"
docker compose up -d mysql redis langgraph-postgres
docker compose run --rm oa-mysql-schema-migrate
docker compose run --rm agent-event-schema-migrate
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

rm -f "/tmp/${SERVER_TAR}" "/tmp/${ADMIN_TAR}" "${REMOTE_ENV_FILE}"
docker image prune -f >/dev/null 2>&1 || true

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep 'ruoyi-'
curl -fsS "${HEALTH_URL}"
