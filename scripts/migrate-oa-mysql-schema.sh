#!/usr/bin/env bash
set -euo pipefail

# Apply Java/OA schema migrations that are not part of the immutable base dump.
# This is intentionally separate from the LangGraph PostgreSQL migration: the
# two databases have different owners and must not be treated as one schema.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MYSQL_CONTAINER="${OA_MYSQL_CONTAINER:-ruoyi-mysql}"
MYSQL_DATABASE="${OA_MYSQL_DATABASE:-ruoyi-vue-pro}"
MYSQL_USER="${OA_MYSQL_USER:-root}"
MYSQL_PASSWORD="${OA_MYSQL_PASSWORD:-${MYSQL_ROOT_PASSWORD:-}}"
SCHEMA_FILES=(
  "${ROOT_DIR}/sql/mysql/system-personal-schedule-init.sql"
  "${ROOT_DIR}/sql/mysql/agent_personal_schedule_effect.sql"
  "${ROOT_DIR}/sql/mysql/party-file-kod-schema-v2.sql"
)

for schema_file in "${SCHEMA_FILES[@]}"; do
  if [ ! -f "${schema_file}" ]; then
    echo "[错误] OA MySQL 迁移文件不存在: ${schema_file}" >&2
    exit 1
  fi
done
if [ -z "${MYSQL_PASSWORD}" ] || [[ "${MYSQL_PASSWORD}" == REPLACE_ME* ]]; then
  echo "[错误] 未配置 OA MySQL 密码，请设置 OA_MYSQL_PASSWORD 或 MYSQL_ROOT_PASSWORD" >&2
  exit 1
fi
if ! docker inspect "${MYSQL_CONTAINER}" >/dev/null 2>&1; then
  echo "[错误] OA MySQL 容器不存在: ${MYSQL_CONTAINER}" >&2
  exit 1
fi
if [ "$(docker inspect -f '{{.State.Running}}' "${MYSQL_CONTAINER}")" != "true" ]; then
  echo "[步骤] 启动 OA MySQL 容器"
  docker start "${MYSQL_CONTAINER}" >/dev/null
fi

echo "[步骤] 等待 OA MySQL 就绪"
for attempt in $(seq 1 60); do
  if docker exec "${MYSQL_CONTAINER}" mysqladmin ping -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" --silent >/dev/null 2>&1; then
    break
  fi
  if [ "${attempt}" -eq 60 ]; then
    echo "[错误] OA MySQL 在 120 秒内未就绪" >&2
    exit 1
  fi
  sleep 2
done

for schema_file in "${SCHEMA_FILES[@]}"; do
  echo "[步骤] 应用 OA MySQL 迁移 $(basename "${schema_file}")"
  docker exec -i "${MYSQL_CONTAINER}" mysql --default-character-set=utf8mb4 \
    -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}" < "${schema_file}"
done
echo "[完成] OA MySQL canonical schema 已对齐"
