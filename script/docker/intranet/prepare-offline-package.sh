#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "用法：$0 --image-archive /本机路径/ghy-oa-intranet-images.tar --target daiwei@192.168.1.103" >&2
  exit 2
}

image_archive=''
target=''
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --image-archive)
      [[ "$#" -ge 2 ]] || usage
      image_archive="$2"
      shift 2
      ;;
    --target)
      [[ "$#" -ge 2 ]] || usage
      target="$2"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

[[ -n "${image_archive}" && -n "${target}" ]] || usage
[[ -f "${image_archive}" ]] || { echo "镜像包不存在：${image_archive}" >&2; exit 1; }

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly REMOTE_DIR=/home/daiwei/oa-deploy
readonly IMAGE_NAME=ghy-oa-intranet-images.tar
readonly PACKAGE_DIR="$(mktemp -d)"
trap 'rm -rf "${PACKAGE_DIR}"' EXIT

copy_file() {
  local source="$1"
  local target_path="$2"
  mkdir -p "${PACKAGE_DIR}/$(dirname "${target_path}")"
  cp "${REPO_ROOT}/${source}" "${PACKAGE_DIR}/${target_path}"
}

copy_file script/docker/intranet/kodbox-compose.yml kodbox-compose.yml
copy_file script/docker/intranet/ghy-oa-compose.yml ghy-oa-compose.yml
copy_file script/docker/intranet/ghy-oa.env.example ghy-oa.env.example
copy_file script/docker/intranet/install-on-target.sh install-on-target.sh
copy_file sql/mysql/ruoyi-vue-pro.sql ruoyi-vue-pro.sql
copy_file script/kodbox/kodbox-sso-fields.patch kodbox-sso-fields.patch
copy_file script/kodbox/sync-oa-entry-plugins.sh sync-oa-entry-plugins.sh
copy_file script/kodbox/oaDeptSync/app.php oaDeptSync/app.php
copy_file script/kodbox/oaDeptSync/package.json oaDeptSync/package.json

(
  cd "${PACKAGE_DIR}"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS
  shasum -a 256 "${image_archive}" | awk -v name="${IMAGE_NAME}" '{print $1 "  " name}' >> SHA256SUMS
)

ssh "${target}" "mkdir -p ${REMOTE_DIR}/oaDeptSync"
scp -r "${PACKAGE_DIR}/"* "${target}:${REMOTE_DIR}/"
scp "${image_archive}" "${target}:${REMOTE_DIR}/${IMAGE_NAME}"
ssh "${target}" "cd ${REMOTE_DIR} && sha256sum -c SHA256SUMS"

echo "上传完成：${target}:${REMOTE_DIR}"
echo "下一步在服务器执行：sudo bash ${REMOTE_DIR}/install-on-target.sh"
