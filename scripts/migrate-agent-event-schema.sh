#!/usr/bin/env bash
set -euo pipefail

# The canonical Agent event-store schema is migration-owned, not Java-owned.
# This script is the local development entry point; production uses the
# equivalent `agent-event-schema-migrate` Compose job.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Java/OA owns the MySQL business schema. Run its canonical migration before
# the Java process starts, but keep it as a separately callable script so
# production deployments can use the same step without coupling PostgreSQL
# credentials to MySQL credentials.
if [ "${OA_MYSQL_SCHEMA_MIGRATION_ENABLED:-true}" = "true" ]; then
  "${ROOT_DIR}/scripts/migrate-oa-mysql-schema.sh"
fi

POSTGRES_CONTAINER="${AGENT_EVENT_POSTGRES_CONTAINER:-kodagent-langgraph-postgres}"
POSTGRES_USER="${LANGGRAPH_POSTGRES_USER:-langgraph}"
POSTGRES_DATABASE="${LANGGRAPH_POSTGRES_DB:-langgraph}"
SCHEMA_FILES=(
  "${ROOT_DIR}/sql/postgresql/agent_run_event.sql"
  "${ROOT_DIR}/sql/postgresql/agent_runtime.sql"
  "${ROOT_DIR}/sql/postgresql/agent_model_config.sql"
  "${ROOT_DIR}/sql/postgresql/party_knowledge.sql"
  "${ROOT_DIR}/sql/postgresql/party_knowledge_vector.sql"
  "${ROOT_DIR}/sql/postgresql/project_agent.sql"
  "${ROOT_DIR}/sql/postgresql/agent_artifact.sql"
)

for schema_file in "${SCHEMA_FILES[@]}"; do
  if [ ! -f "${schema_file}" ]; then
    echo "[错误] Agent PostgreSQL 迁移文件不存在: ${schema_file}" >&2
    exit 1
  fi
done

if ! docker inspect "${POSTGRES_CONTAINER}" >/dev/null 2>&1; then
  echo "[错误] Agent PostgreSQL 容器不存在: ${POSTGRES_CONTAINER}" >&2
  echo "[提示] 请先启动 script/docker/docker-compose.yml 中的 langgraph-postgres 服务" >&2
  exit 1
fi
if [ "$(docker inspect -f '{{.State.Running}}' "${POSTGRES_CONTAINER}")" != "true" ]; then
  echo "[步骤] 启动 Agent PostgreSQL 容器"
  docker start "${POSTGRES_CONTAINER}" >/dev/null
fi

echo "[步骤] 等待 Agent PostgreSQL 就绪"
for attempt in $(seq 1 60); do
  if docker exec "${POSTGRES_CONTAINER}" \
      pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DATABASE}" >/dev/null 2>&1; then
    break
  fi
  if [ "${attempt}" -eq 60 ]; then
    echo "[错误] Agent PostgreSQL 在 120 秒内未就绪" >&2
    exit 1
  fi
  sleep 2
done

echo "[步骤] 应用 Agent PostgreSQL canonical schema"
for schema_file in "${SCHEMA_FILES[@]}"; do
  echo "[步骤] 迁移 $(basename "${schema_file}")"
  docker exec -i "${POSTGRES_CONTAINER}" \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DATABASE}" < "${schema_file}"
done
