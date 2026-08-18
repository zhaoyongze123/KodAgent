#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOADER="${ROOT_DIR}/script/docker/env/load-target-env.sh"
TARGET_ENV_NAME="${1:-}"

if [[ -z "${TARGET_ENV_NAME}" ]]; then
  echo "用法：$0 local|103|production" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "${LOADER}" "${TARGET_ENV_NAME}"

required_values=(
  TARGET_ENV DEPLOY_MODE APP_ENV SPRING_PROFILES_ACTIVE
  INTRANET_HOST OA_PUBLIC_URL INTRANET_APP_ORIGIN OA_BACKEND_PORT OA_FRONTEND_PORT
  KODBOX_PUBLIC_URL KODBOX_SERVER_URL PREVIEW_PUBLIC_URL PREVIEW_IMAGE PREVIEW_CONTAINER PREVIEW_BIND_HOST PREVIEW_HOST_PORT PREVIEW_CONTAINER_PORT
  OA_ROOT OA_DB_ROOT OA_APP_ROOT MYSQL_DATABASE MYSQL_PORT REDIS_PORT REDIS_INTERNAL_PORT SERVER_PORT ADMIN_PORT
  MASTER_DATASOURCE_URL MASTER_DATASOURCE_USERNAME SLAVE_DATASOURCE_URL SLAVE_DATASOURCE_USERNAME REDIS_HOST REDIS_DATABASE
  HEALTH_URL FRONTEND_URL FRONTEND_ENV_FILE FILE_PREVIEW_URL
  KOD_SSO_ENABLED KOD_SSO_BASE_URL KOD_SSO_SERVER_BASE_URL KOD_SSO_APP_NAME KOD_SSO_REDIRECT_URI KOD_SSO_CALLBACK_BASE_URL KOD_SSO_TENANT_ID
)

for name in "${required_values[@]}"; do
  value="${!name:-}"
  if [[ -z "${value}" || "${value}" == CHANGE_ME* || "${value}" == REPLACE_ME* ]]; then
    echo "[错误] ${name} 未配置。文件：${TARGET_ENV_FILE}" >&2
    exit 1
  fi
done

case "${TARGET_ENV}:${DEPLOY_MODE}" in
  local:docker-compose|103:manual|production:manual) ;;
  *)
    echo "[错误] ${TARGET_ENV} 的部署模式不符合约定：${DEPLOY_MODE}" >&2
    exit 1
    ;;
esac

[[ "${PREVIEW_IMAGE}" == "keking/kkfileview:4.1.0" ]] || {
  echo "[错误] 预览镜像必须固定为 keking/kkfileview:4.1.0：${PREVIEW_IMAGE}" >&2
  exit 1
}

[[ "${INTRANET_APP_ORIGIN}" == "${OA_PUBLIC_URL}" ]] || {
  echo "[错误] INTRANET_APP_ORIGIN 与 OA_PUBLIC_URL 不一致。" >&2
  exit 1
}
[[ "${OA_BACKEND_PORT}" == "${SERVER_PORT}" && "${OA_FRONTEND_PORT}" == "${ADMIN_PORT}" ]] || {
  echo "[错误] OA 对外端口与应用映射端口不一致。" >&2
  exit 1
}
[[ "${PREVIEW_PUBLIC_URL}" == "${PREVIEW_PUBLIC_URL%/}" ]] || {
  echo "[错误] PREVIEW_PUBLIC_URL 不应以 / 结尾：${PREVIEW_PUBLIC_URL}" >&2
  exit 1
}

frontend_file="${FRONTEND_ENV_FILE}"
if [[ "${frontend_file}" != /* ]]; then
  frontend_file="${ROOT_DIR}/${frontend_file}"
fi
[[ -f "${frontend_file}" ]] || {
  echo "[错误] 前端环境文件不存在：${frontend_file}" >&2
  exit 1
}

frontend_preview="$(sed -nE 's/^VITE_(GLOB_)?FILE_PREVIEW_URL=//p' "${frontend_file}" | tail -n 1)"
expected_preview="${PREVIEW_PUBLIC_URL%/}/onlinePreview"
[[ "${FILE_PREVIEW_URL}" == "${expected_preview}" && -z "${frontend_preview}" ]] || {
  echo "[错误] 文件预览配置不符合运行时注入约定：profile=${FILE_PREVIEW_URL}, frontend=${frontend_preview}, expected=${expected_preview}" >&2
  echo "[提示] 前端构建环境文件不得配置 VITE_FILE_PREVIEW_URL 或 VITE_GLOB_FILE_PREVIEW_URL，具体地址由目标服务器生成 oa-runtime-config.js。" >&2
  exit 1
}

for name in OA_BACKEND_PORT OA_FRONTEND_PORT PREVIEW_HOST_PORT PREVIEW_CONTAINER_PORT MYSQL_PORT REDIS_PORT REDIS_INTERNAL_PORT SERVER_PORT ADMIN_PORT; do
  value="${!name}"
  [[ "${value}" =~ ^[0-9]+$ && "${value}" -ge 1 && "${value}" -le 65535 ]] || {
    echo "[错误] ${name} 不是有效端口：${value}" >&2
    exit 1
  }
done

for url_name in OA_PUBLIC_URL INTRANET_APP_ORIGIN KODBOX_PUBLIC_URL KODBOX_SERVER_URL PREVIEW_PUBLIC_URL HEALTH_URL FRONTEND_URL FILE_PREVIEW_URL KOD_SSO_BASE_URL KOD_SSO_SERVER_BASE_URL KOD_SSO_REDIRECT_URI KOD_SSO_CALLBACK_BASE_URL; do
  url_value="${!url_name}"
  [[ "${url_value}" =~ ^https?:// ]] || {
    echo "[错误] ${url_name} 不是 http(s) 地址：${url_value}" >&2
    exit 1
  }
done

if [[ "${TARGET_SECRETS_LOADED:-false}" == true ]]; then
  secret_names=(MYSQL_ROOT_PASSWORD MASTER_DATASOURCE_PASSWORD SLAVE_DATASOURCE_PASSWORD REDIS_PASSWORD)
  for name in "${secret_names[@]}"; do
    value="${!name:-}"
    if [[ -z "${value}" || "${value}" == CHANGE_ME* || "${value}" == REPLACE_ME* ]]; then
      echo "[错误] ${name} 仍是空值或占位符：${TARGET_SECRETS_PATH}" >&2
      exit 1
    fi
  done
else
  echo "[警告] 未找到 ${TARGET_SECRETS_PATH}；当前只完成非机密配置校验。" >&2
fi

printf 'target_env=%s\n' "${TARGET_ENV}"
printf 'deploy_mode=%s\n' "${DEPLOY_MODE}"
printf 'oa_public_url=%s\n' "${OA_PUBLIC_URL}"
printf 'frontend_env=%s\n' "${FRONTEND_ENV_FILE}"
printf 'preview_url=%s\n' "${FILE_PREVIEW_URL}"
printf 'validation=ok\n'
