#!/usr/bin/env bash
set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly OUTPUT_DIR="${1:-${REPO_ROOT}}"
readonly BUNDLE_DIR_NAME=ghy-oa-intranet-offline-20260731-r2
readonly BUNDLE_NAME="${BUNDLE_DIR_NAME}.tar.gz"
readonly WORK_DIR="$(mktemp -d)"
readonly BUNDLE_DIR="${WORK_DIR}/${BUNDLE_DIR_NAME}"
trap 'rm -rf "${WORK_DIR}"' EXIT

mkdir -p "${BUNDLE_DIR}" "${OUTPUT_DIR}"

images=(
  kodcloud/kodbox:latest
  docker.m.daocloud.io/library/mysql:8
  docker.m.daocloud.io/library/redis:6-alpine
  ghy-oa-server:20260731-r2
  ghy-oa-admin:20260731-r2
)
for image in "${images[@]}"; do
  docker image inspect "${image}" >/dev/null 2>&1 || {
    echo "缺少本地 Docker 镜像：${image}" >&2
    exit 1
  }
done

copy_file() {
  local source="$1"
  local target_path="$2"
  mkdir -p "${BUNDLE_DIR}/$(dirname "${target_path}")"
  cp "${REPO_ROOT}/${source}" "${BUNDLE_DIR}/${target_path}"
}

copy_file script/docker/intranet/install-on-target.sh install-on-target.sh
copy_file script/docker/intranet/kodbox-compose.yml kodbox-compose.yml
copy_file script/docker/intranet/ghy-oa.env.example ghy-oa.env.example
copy_file script/kodbox/kodbox-sso-fields.patch kodbox-sso-fields.patch
copy_file script/kodbox/sync-oa-entry-plugins.sh sync-oa-entry-plugins.sh
copy_file script/kodbox/oaDeptSync/app.php oaDeptSync/app.php
copy_file script/kodbox/oaDeptSync/package.json oaDeptSync/package.json
copy_file sql/mysql/ruoyi-vue-pro.sql ruoyi-vue-pro.sql

sed \
  -e 's/ghy-oa-server:20260731/ghy-oa-server:20260731-r2/g' \
  -e 's/ghy-oa-admin:20260731/ghy-oa-admin:20260731-r2/g' \
  "${REPO_ROOT}/script/docker/intranet/ghy-oa-compose.yml" \
  > "${BUNDLE_DIR}/ghy-oa-compose.yml"

docker save -o "${BUNDLE_DIR}/ghy-oa-intranet-images.tar" "${images[@]}"

printf '%s\n' \
  'BUNDLE_VERSION=20260731-r2' \
  'BUNDLE_NAME=ghy-oa-intranet-offline-20260731-r2' \
  'SERVER_IMAGE=ghy-oa-server:20260731-r2' \
  'ADMIN_IMAGE=ghy-oa-admin:20260731-r2' \
  'IMAGE_ARCHIVE=ghy-oa-intranet-images.tar' \
  'TARGET_IP=192.168.1.103' \
  > "${BUNDLE_DIR}/manifest.env"

(
  cd "${BUNDLE_DIR}"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
)

tar -czf "${OUTPUT_DIR}/${BUNDLE_NAME}" -C "${WORK_DIR}" "${BUNDLE_DIR_NAME}"
shasum -a 256 "${OUTPUT_DIR}/${BUNDLE_NAME}"
printf '离线包已生成：%s\n' "${OUTPUT_DIR}/${BUNDLE_NAME}"
