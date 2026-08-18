#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOADER="${ROOT_DIR}/script/docker/env/load-target-env.sh"
ENSURE="${ROOT_DIR}/script/docker/intranet/ensure-preview-target.sh"
COMPOSE_FILE="${ROOT_DIR}/script/docker/intranet/preview-compose.yml"
TARGET_ENV_NAME="${1:-}"

if [[ -z "${TARGET_ENV_NAME}" ]]; then
  echo "用法：$0 local|103|production" >&2
  exit 2
fi

bash "${ENSURE}" "${TARGET_ENV_NAME}"
# shellcheck disable=SC1090
source "${LOADER}" "${TARGET_ENV_NAME}"

command -v curl >/dev/null 2>&1 || { echo '[错误] 缺少 curl。' >&2; exit 1; }
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo '[错误] 缺少 docker compose 或 docker-compose。' >&2
  exit 1
fi

compose_env_args=(--env-file "${TARGET_ENV_FILE}")

# 103 上的预览容器可能是早期 docker run 创建的，没有 Compose labels。
# 如果它已经符合当前 profile，直接复用，避免同名容器冲突；不符合时明确失败，
# 不自动删除现场容器。
if docker inspect "${PREVIEW_CONTAINER}" >/dev/null 2>&1; then
  existing_image="$(docker inspect -f '{{.Config.Image}}' "${PREVIEW_CONTAINER}")"
  existing_base_url="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${PREVIEW_CONTAINER}" | sed -n 's/^KK_BASE_URL=//p' | head -n 1)"
  existing_port="$(docker port "${PREVIEW_CONTAINER}" 8012/tcp 2>/dev/null | head -n 1 || true)"
  if [[ "${existing_image}" != "${PREVIEW_IMAGE}" || "${existing_base_url}" != "${PREVIEW_PUBLIC_URL}" || "${existing_port}" != *":${PREVIEW_HOST_PORT}"* ]]; then
    echo "[错误] 已存在的预览容器与 ${TARGET_ENV} profile 不一致：${PREVIEW_CONTAINER}" >&2
    echo "image=${existing_image} base_url=${existing_base_url} port=${existing_port}" >&2
    echo "请在维护窗口手动停止并删除该预览容器后再执行本脚本。" >&2
    exit 1
  fi
  if [[ "$(docker inspect -f '{{.State.Status}}' "${PREVIEW_CONTAINER}")" != running ]]; then
    docker start "${PREVIEW_CONTAINER}" >/dev/null
  fi
else
  "${COMPOSE[@]}" "${compose_env_args[@]}" -f "${COMPOSE_FILE}" up -d --no-build preview
fi

for attempt in $(seq 1 30); do
  if curl -fsS --max-time 5 "http://${PREVIEW_BIND_HOST}:${PREVIEW_HOST_PORT}/" >/dev/null 2>&1; then
    break
  fi
  if [[ "${attempt}" -eq 30 ]]; then
    echo "[错误] 预览服务未通过检查：http://${PREVIEW_BIND_HOST}:${PREVIEW_HOST_PORT}/" >&2
    docker logs --tail 100 "${PREVIEW_CONTAINER}" >&2 || true
    exit 1
  fi
  sleep 2
done

actual_base_url="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${PREVIEW_CONTAINER}" | sed -n 's/^KK_BASE_URL=//p' | head -n 1)"
[[ "${actual_base_url}" == "${PREVIEW_PUBLIC_URL}" ]] || {
  echo "[错误] KK_BASE_URL 与目标 profile 不一致：${actual_base_url} != ${PREVIEW_PUBLIC_URL}" >&2
  exit 1
}

docker ps --filter "name=^/${PREVIEW_CONTAINER}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
printf 'preview_apply_ok\n'
printf 'target_env=%s\n' "${TARGET_ENV}"
printf 'public_preview_url=%s\n' "${PREVIEW_PUBLIC_URL}"
