#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_ENV="${DEPLOY_ENV:-stage}"
TARGET_ENV="${TARGET_ENV:-}"
TARGET_PROFILE_MODE=false
if [[ -z "${TARGET_ENV}" && "${DEPLOY_ENV}" =~ ^(local|103|production)$ ]]; then
  TARGET_ENV="${DEPLOY_ENV}"
fi
if [[ -n "${TARGET_ENV}" ]]; then
  TARGET_PROFILE_MODE=true
fi
ENV_FILE="${DEPLOY_ENV_FILE:-${ROOT_DIR}/script/docker/env/${DEPLOY_ENV}.env}"
ENV_EXAMPLE_FILE="${DEPLOY_ENV_EXAMPLE_FILE:-${ROOT_DIR}/script/docker/env/${DEPLOY_ENV}.env.example}"
SERVER_IMAGE="${SERVER_IMAGE:-ruoyi-server:local}"
ADMIN_IMAGE="${ADMIN_IMAGE:-ruoyi-admin:local}"
SERVER_TAR="${SERVER_TAR:-ruoyi-server-local.tar}"
ADMIN_TAR="${ADMIN_TAR:-ruoyi-admin-local.tar}"
DB_NAME="${DB_NAME:-ruoyi-vue-pro}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
LOCAL_DB_HOST="${LOCAL_DB_HOST:-127.0.0.1}"
LOCAL_DB_PORT="${LOCAL_DB_PORT:-3306}"
LOCAL_DB_USER="${LOCAL_DB_USER:-root}"
LOCAL_DB_PASSWORD="${LOCAL_DB_PASSWORD:-123456}"
REMOTE_DB_CONTAINER="${REMOTE_DB_CONTAINER:-ruoyi-mysql}"
DB_DUMP_GZ="${DB_DUMP_GZ:-ruoyi-vue-pro.sql.gz}"
IMPORT_DATABASE="${IMPORT_DATABASE:-false}"
REMOTE_ENV_BASENAME="${REMOTE_ENV_BASENAME:-ruoyi-deploy.env}"
CLEAN_LOCAL_ARTIFACTS="${CLEAN_LOCAL_ARTIFACTS:-true}"
CLEAN_LOCAL_DOCKER_CACHE="${CLEAN_LOCAL_DOCKER_CACHE:-true}"
TARGET_LOADER="${ROOT_DIR}/script/docker/env/load-target-env.sh"
TARGET_VALIDATOR="${ROOT_DIR}/script/docker/env/validate-target-env.sh"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[错误] 缺少命令: $1" >&2
    exit 1
  fi
}

cleanup_local_artifacts() {
  if [ "${CLEAN_LOCAL_ARTIFACTS}" = "true" ]; then
    rm -f "${ROOT_DIR}/${SERVER_TAR}" "${ROOT_DIR}/${ADMIN_TAR}" "${ROOT_DIR}/${DB_DUMP_GZ}"
  fi
}

remove_old_local_repo_tags() {
  local current_image="$1"
  local current_repo="${current_image%%:*}"
  local current_tag="${current_image#*:}"
  local image_refs

  image_refs="$(
    docker images --format '{{.Repository}}:{{.Tag}}' "${current_repo}" 2>/dev/null \
      | awk -F: -v repo="${current_repo}" -v keep_tag="${current_tag}" '
          $1 == repo && $2 != "<none>" && $2 != keep_tag {
            print $0
          }
        '
  )"

  if [ -z "${image_refs}" ]; then
    return
  fi

  while IFS= read -r image_ref; do
    [ -n "${image_ref}" ] || continue
    echo "[步骤] 删除本地旧镜像标签 ${image_ref}"
    docker rmi "${image_ref}" >/dev/null 2>&1 || true
  done <<<"${image_refs}"
}

cleanup_local_docker_artifacts() {
  if [ "${CLEAN_LOCAL_DOCKER_CACHE}" = "true" ]; then
    remove_old_local_repo_tags "${SERVER_IMAGE}"
    remove_old_local_repo_tags "${ADMIN_IMAGE}"
    docker image prune -f >/dev/null 2>&1 || true
    docker builder prune -f >/dev/null 2>&1 || true
  fi
}

cleanup_local() {
  cleanup_local_artifacts
  cleanup_local_docker_artifacts
}

load_env_file() {
  if [ "${TARGET_PROFILE_MODE}" = "true" ]; then
    if [ ! -f "${TARGET_LOADER}" ]; then
      echo "[错误] 目标环境加载器不存在: ${TARGET_LOADER}" >&2
      exit 1
    fi
    # shellcheck disable=SC1090
    source "${TARGET_LOADER}" "${TARGET_ENV}"
    DEPLOY_ENV="${TARGET_ENV}"
    ENV_FILE="${TARGET_ENV_FILE}"
    DB_NAME="${MYSQL_DATABASE:-${DB_NAME}}"
    REMOTE_DB_CONTAINER="${MYSQL_CONTAINER:-${REMOTE_DB_CONTAINER}}"
    FRONTEND_ENV_FILE="${FRONTEND_ENV_FILE:?目标环境未设置 FRONTEND_ENV_FILE}"
    INTRANET_APP_ORIGIN="${INTRANET_APP_ORIGIN:?目标环境未设置 INTRANET_APP_ORIGIN}"
    HEALTH_URL="${HEALTH_URL:?目标环境未设置 HEALTH_URL}"
    SERVER_PORT="${SERVER_PORT:?目标环境未设置 SERVER_PORT}"
    ADMIN_PORT="${ADMIN_PORT:?目标环境未设置 ADMIN_PORT}"
    return 0
  fi

  if [ ! -f "${ENV_FILE}" ]; then
    if [ -f "${ENV_EXAMPLE_FILE}" ]; then
      echo "[提示] 未找到环境文件，回退到示例文件: ${ENV_EXAMPLE_FILE}"
      ENV_FILE="${ENV_EXAMPLE_FILE}"
    else
      echo "[错误] 环境文件不存在: ${ENV_FILE}" >&2
      exit 1
    fi
  fi
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

validate_target_profile() {
  if [ ! -x "${TARGET_VALIDATOR}" ]; then
    echo "[错误] 目标环境校验器不存在或不可执行: ${TARGET_VALIDATOR}" >&2
    exit 1
  fi
  bash "${TARGET_VALIDATOR}" "${TARGET_ENV}" >/dev/null
}

require_target_secrets() {
  if [ "${TARGET_SECRETS_LOADED:-false}" != "true" ]; then
    echo "[错误] 未找到目标环境机密文件: ${TARGET_SECRETS_PATH}" >&2
    echo "请先复制对应的 .secrets.env.example 并填写真实值。" >&2
    exit 1
  fi
  local name value
  for name in MYSQL_ROOT_PASSWORD MASTER_DATASOURCE_PASSWORD SLAVE_DATASOURCE_PASSWORD REDIS_PASSWORD; do
    value="${!name:-}"
    if [ -z "${value}" ] || [[ "${value}" == CHANGE_ME* || "${value}" == REPLACE_ME* ]]; then
      echo "[错误] ${name} 未配置完成: ${TARGET_SECRETS_PATH}" >&2
      exit 1
    fi
  done
}

target_compose() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    echo "[错误] 缺少 docker compose 或 docker-compose。" >&2
    exit 1
  fi
  # Secrets are exported by load-target-env.sh; use one --env-file for compatibility
  # with older docker-compose releases that accept only a single env file.
  COMPOSE_ENV_ARGS=(--env-file "${TARGET_ENV_FILE}")
}

deploy_target_local() {
  require_target_secrets
  require_cmd docker
  require_cmd curl
  target_compose

  echo "[步骤] 构建后端 jar（目标环境: ${TARGET_ENV}）"
  (cd "${ROOT_DIR}" && mvn -pl yudao-server -am -DskipTests package)
  echo "[步骤] 启动本地目标环境 Compose"
  "${COMPOSE[@]}" "${COMPOSE_ENV_ARGS[@]}" \
    -f "${ROOT_DIR}/script/docker/docker-compose.yml" up -d --build

  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 5 "${HEALTH_URL}" >/dev/null 2>&1; then
      echo "[完成] ${TARGET_ENV} 后端健康检查通过: ${HEALTH_URL}"
      return 0
    fi
    sleep 2
  done
  echo "[错误] ${TARGET_ENV} 后端健康检查失败: ${HEALTH_URL}" >&2
  "${COMPOSE[@]}" "${COMPOSE_ENV_ARGS[@]}" \
    -f "${ROOT_DIR}/script/docker/docker-compose.yml" ps >&2 || true
  exit 1
}

reject_manual_target() {
  echo "[停止] 目标环境 ${TARGET_ENV} 是手工部署形态（宿主机 JAR + 既有 Nginx）。" >&2
  echo "deploy.sh 不会把它误当成 Docker Compose 目标重建。" >&2
  echo "请在目标服务器使用 script/docker/intranet/update-oa-on-target.sh 更新 JAR/前端，" >&2
  echo "并使用 script/docker/intranet/apply-preview-target.sh ${TARGET_ENV} 管理离线预览服务。" >&2
  exit 2
}

validate_value() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "${value}" ] || [[ "${value}" == REPLACE_ME* ]]; then
    echo "[错误] 环境变量 ${name} 未配置完成，请检查 ${ENV_FILE}" >&2
    exit 1
  fi
}

validate_env() {
  validate_value SPRING_PROFILES_ACTIVE
  validate_value FRONTEND_ENV_FILE
  if [ ! -f "${ROOT_DIR}/${FRONTEND_ENV_FILE}" ]; then
    echo "[错误] 前端环境文件不存在: ${ROOT_DIR}/${FRONTEND_ENV_FILE}" >&2
    exit 1
  fi
  if [ "${TARGET_PROFILE_MODE}" != "true" ] && [ "${DEPLOY_ENV}" != "dev" ]; then
    validate_value REMOTE_HOST
    validate_value REMOTE_USER
    validate_value REMOTE_DEPLOY_DIR
  fi
}

remote_sh() {
  if [ -n "${REMOTE_PASSWORD:-}" ]; then
    sshpass -p "${REMOTE_PASSWORD}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "$@"
  else
    ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "$@"
  fi
}

copy_to_remote() {
  if [ -n "${REMOTE_PASSWORD:-}" ]; then
    sshpass -p "${REMOTE_PASSWORD}" scp -o StrictHostKeyChecking=no "$1" "${REMOTE_USER}@${REMOTE_HOST}:$2"
  else
    scp -o StrictHostKeyChecking=no "$1" "${REMOTE_USER}@${REMOTE_HOST}:$2"
  fi
}

build_backend_jar() {
  echo "[步骤] 构建后端 jar"
  (cd "${ROOT_DIR}" && mvn -pl yudao-server -am -DskipTests package)
}

build_images() {
  echo "[步骤] 构建后端镜像 ${SERVER_IMAGE}"
  (cd "${ROOT_DIR}" && docker buildx build --platform "${DOCKER_PLATFORM}" --load -f script/docker/backend.Dockerfile -t "${SERVER_IMAGE}" .)

  echo "[步骤] 构建前端镜像 ${ADMIN_IMAGE}，环境文件 ${FRONTEND_ENV_FILE}"
  (cd "${ROOT_DIR}" && docker buildx build --platform "${DOCKER_PLATFORM}" --load \
    --build-arg FRONTEND_ENV_FILE="${FRONTEND_ENV_FILE}" \
    --build-arg INTRANET_APP_ORIGIN="${INTRANET_APP_ORIGIN:-http://${REMOTE_HOST:-127.0.0.1}:${ADMIN_PORT:-18080}}" \
    -f script/docker/frontend.Dockerfile -t "${ADMIN_IMAGE}" .)
}

dump_database() {
  echo "[步骤] 导出本地数据库 ${DB_NAME}"
  rm -f "${ROOT_DIR}/${DB_DUMP_GZ}"
  mysqldump \
    -h"${LOCAL_DB_HOST}" \
    -P"${LOCAL_DB_PORT}" \
    -u"${LOCAL_DB_USER}" \
    -p"${LOCAL_DB_PASSWORD}" \
    --single-transaction \
    --routines \
    --triggers \
    --default-character-set=utf8mb4 \
    --set-gtid-purged=OFF \
    "${DB_NAME}" | gzip > "${ROOT_DIR}/${DB_DUMP_GZ}"
}

save_images() {
  echo "[步骤] 导出镜像 tar"
  rm -f "${ROOT_DIR}/${SERVER_TAR}" "${ROOT_DIR}/${ADMIN_TAR}"
  (cd "${ROOT_DIR}" && docker save -o "${SERVER_TAR}" "${SERVER_IMAGE}")
  (cd "${ROOT_DIR}" && docker save -o "${ADMIN_TAR}" "${ADMIN_IMAGE}")
}

upload_artifacts() {
  echo "[步骤] 上传镜像到 ${REMOTE_HOST}"
  remote_sh "mkdir -p '${REMOTE_DEPLOY_DIR}'"
  copy_to_remote "${ROOT_DIR}/${SERVER_TAR}" "/tmp/${SERVER_TAR}"
  copy_to_remote "${ROOT_DIR}/${ADMIN_TAR}" "/tmp/${ADMIN_TAR}"
  copy_to_remote "${ROOT_DIR}/script/docker/remote-reload-app.sh" "/tmp/remote-reload-app.sh"
  copy_to_remote "${ROOT_DIR}/script/docker/docker-compose.yml" "${REMOTE_DEPLOY_DIR}/docker-compose.yml"
  if [ "${IMPORT_DATABASE}" = "true" ]; then
    copy_to_remote "${ROOT_DIR}/${DB_DUMP_GZ}" "/tmp/${DB_DUMP_GZ}"
  fi
}

deploy_remote_app_only() {
  echo "[步骤] 远端重载应用（不覆盖数据库）"
  remote_sh "chmod +x /tmp/remote-reload-app.sh && REMOTE_DEPLOY_DIR='${REMOTE_DEPLOY_DIR}' SERVER_TAR='${SERVER_TAR}' ADMIN_TAR='${ADMIN_TAR}' /tmp/remote-reload-app.sh && rm -f /tmp/remote-reload-app.sh"
}

deploy_remote_with_db() {
  echo "[步骤] 远端停旧服务、导入镜像并覆盖数据库"
  remote_sh \
    "REMOTE_DEPLOY_DIR='${REMOTE_DEPLOY_DIR}' SERVER_TAR='${SERVER_TAR}' ADMIN_TAR='${ADMIN_TAR}' DB_DUMP_GZ='${DB_DUMP_GZ}' REMOTE_DB_CONTAINER='${REMOTE_DB_CONTAINER}' DB_NAME='${DB_NAME}' REMOTE_ENV_BASENAME='${REMOTE_ENV_BASENAME}' bash -s" <<'EOF'
set -euo pipefail

if [ -f "${REMOTE_DEPLOY_DIR}/.env" ]; then
  set -a
  source "${REMOTE_DEPLOY_DIR}/.env"
  set +a
elif [ -f "/tmp/${REMOTE_ENV_BASENAME}" ]; then
  set -a
  source "/tmp/${REMOTE_ENV_BASENAME}"
  set +a
fi

cd "${REMOTE_DEPLOY_DIR}"
docker compose up -d mysql redis
for i in $(seq 1 60); do
  if docker exec "${REMOTE_DB_CONTAINER}" mysqladmin ping -uroot -p123456 --silent >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then
    echo "[错误] MySQL 在 120 秒内未就绪" >&2
    exit 1
  fi
done
printf 'DROP DATABASE IF EXISTS `%s`; CREATE DATABASE `%s` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;' "${DB_NAME}" "${DB_NAME}" | docker exec -i "${REMOTE_DB_CONTAINER}" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}"
gzip -dc "/tmp/${DB_DUMP_GZ}" | docker exec -i "${REMOTE_DB_CONTAINER}" mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" "${DB_NAME}"
docker compose stop server admin || true
docker compose rm -sf server admin || true
docker load -i "/tmp/${SERVER_TAR}"
docker load -i "/tmp/${ADMIN_TAR}"
docker compose up -d --no-build server admin
rm -f "/tmp/${SERVER_TAR}" "/tmp/${ADMIN_TAR}" "/tmp/${DB_DUMP_GZ}" "/tmp/${REMOTE_ENV_BASENAME}" /tmp/remote-reload-app.sh
docker image prune -f >/dev/null 2>&1 || true
EOF
  remote_sh "curl -fsS http://127.0.0.1:48080/actuator/health"
}

print_summary() {
  echo "[完成] 环境 ${DEPLOY_ENV} 已部署到 ${REMOTE_HOST:-local}"
  echo "[提示] 前端预览地址: http://${REMOTE_HOST:-127.0.0.1}:${ADMIN_PORT:-18080}"
  echo "[提示] 后端健康检查: http://${REMOTE_HOST:-127.0.0.1}:${SERVER_PORT:-48080}/actuator/health"
  if [ "${CLEAN_LOCAL_ARTIFACTS}" = "true" ]; then
    echo "[提示] 本地导出镜像和临时数据库包已自动清理"
  fi
  if [ "${CLEAN_LOCAL_DOCKER_CACHE}" = "true" ]; then
    echo "[提示] 本地旧版 ruoyi 镜像标签、未使用的 Docker 镜像和构建缓存已自动清理"
  fi
}

main() {
  trap cleanup_local EXIT

  load_env_file
  if [ "${TARGET_PROFILE_MODE}" = "true" ]; then
    validate_target_profile
    case "${TARGET_ENV}" in
      local)
        deploy_target_local
        print_summary
        exit 0
        ;;
      103|production)
        reject_manual_target
        ;;
    esac
  fi
  require_cmd mvn
  require_cmd docker
  require_cmd gzip
  validate_env
  if [ "${DEPLOY_ENV}" != "dev" ]; then
    require_cmd scp
    require_cmd ssh
    require_cmd curl
    if [ -n "${REMOTE_PASSWORD:-}" ]; then
      require_cmd sshpass
    fi
  fi
  if [ "${IMPORT_DATABASE}" = "true" ]; then
    require_cmd mysqldump
  fi

  build_backend_jar
  build_images
  if [ "${IMPORT_DATABASE}" = "true" ]; then
    dump_database
  fi
  save_images
  upload_artifacts
  if [ "${IMPORT_DATABASE}" = "true" ]; then
    deploy_remote_with_db
  else
    deploy_remote_app_only
  fi
  print_summary
}

main "$@"
