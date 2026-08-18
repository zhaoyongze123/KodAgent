#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOADER="${ROOT_DIR}/script/docker/env/load-target-env.sh"
COMPOSE_FILE="${ROOT_DIR}/script/docker/intranet/preview-compose.yml"
TARGET_ENV_NAME="${1:-}"

if [[ -z "${TARGET_ENV_NAME}" ]]; then
  echo "用法：$0 local|103|production" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "${LOADER}" "${TARGET_ENV_NAME}"

command -v docker >/dev/null 2>&1 || { echo '[错误] 缺少 docker。' >&2; exit 1; }
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo '[错误] 缺少 docker compose 或 docker-compose。' >&2
  exit 1
fi

PREVIEW_IMAGE="${PREVIEW_IMAGE:-keking/kkfileview:4.1.0}"
PREVIEW_CONTAINER="${PREVIEW_CONTAINER:-oa-manual-preview}"
PREVIEW_HOST_PORT="${PREVIEW_HOST_PORT:?未配置 PREVIEW_HOST_PORT}"
PREVIEW_BIND_HOST="${PREVIEW_BIND_HOST:?未配置 PREVIEW_BIND_HOST}"
PREVIEW_PUBLIC_URL="${PREVIEW_PUBLIC_URL:?未配置 PREVIEW_PUBLIC_URL}"

docker image inspect "${PREVIEW_IMAGE}" >/dev/null 2>&1 || {
  echo "[错误] 本机没有预览镜像：${PREVIEW_IMAGE}，请先 docker load。" >&2
  exit 1
}

if docker inspect "${PREVIEW_CONTAINER}" >/dev/null 2>&1; then
  existing_port="$(docker port "${PREVIEW_CONTAINER}" 2>/dev/null | head -n 1 || true)"
  echo "预览容器已存在：${PREVIEW_CONTAINER}${existing_port:+ (${existing_port})}"
else
  if command -v ss >/dev/null 2>&1 && ss -lntH 2>/dev/null | awk -v port=":${PREVIEW_HOST_PORT}" '$4 ~ port "$" { found=1 } END { exit !found }'; then
    echo "[错误] 预览宿主机端口已被其他进程占用：${PREVIEW_BIND_HOST}:${PREVIEW_HOST_PORT}" >&2
    exit 1
  fi
fi

[[ "${PREVIEW_PUBLIC_URL}" == "${PREVIEW_PUBLIC_URL%/}" ]] || {
  echo "[错误] PREVIEW_PUBLIC_URL 不应以 / 结尾：${PREVIEW_PUBLIC_URL}" >&2
  exit 1
}

compose_env_args=(--env-file "${TARGET_ENV_FILE}")
"${COMPOSE[@]}" "${compose_env_args[@]}" -f "${COMPOSE_FILE}" config >/dev/null

printf 'preview_target_ok\n'
printf 'target_env=%s\n' "${TARGET_ENV}"
printf 'image=%s\n' "${PREVIEW_IMAGE}"
printf 'container=%s\n' "${PREVIEW_CONTAINER}"
printf 'bind=%s:%s\n' "${PREVIEW_BIND_HOST}" "${PREVIEW_HOST_PORT}"
printf 'kk_base_url=%s\n' "${PREVIEW_PUBLIC_URL}"
