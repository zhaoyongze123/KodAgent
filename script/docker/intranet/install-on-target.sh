#!/usr/bin/env bash
set -euo pipefail

readonly KODBOX_DIR=/data/kodbox
readonly OA_DIR=/data/ghy-oa
readonly STAGING_DIR="${STAGING_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
readonly IMAGE_ARCHIVE="${STAGING_DIR}/ghy-oa-intranet-images.tar"
readonly SSO_PATCH_FILE="${STAGING_DIR}/kodbox-sso-fields.patch"
readonly PLUGIN_SYNC_SCRIPT="${STAGING_DIR}/sync-oa-entry-plugins.sh"

if [[ "${EUID}" -ne 0 ]]; then
  echo 'This installer must run as root.' >&2
  exit 1
fi

required_files=(
  kodbox-compose.yml
  ghy-oa-compose.yml
  ghy-oa.env.example
  ruoyi-vue-pro.sql
  kodbox-sso-fields.patch
  sync-oa-entry-plugins.sh
  oaDeptSync/app.php
  oaDeptSync/package.json
)
for file in "${required_files[@]}"; do
  if [[ ! -f "${STAGING_DIR}/${file}" ]]; then
    echo "Missing deployment file: ${STAGING_DIR}/${file}" >&2
    exit 1
  fi
done
if [[ ! -f "${IMAGE_ARCHIVE}" ]]; then
  echo "Missing image archive: ${IMAGE_ARCHIVE}" >&2
  exit 1
fi

if [[ -e "${OA_DIR}/mysql/auto.cnf" ]]; then
  echo "Existing MySQL data found at ${OA_DIR}/mysql; refusing first-install initialization." >&2
  exit 1
fi

install -d -m 0755 \
  "${KODBOX_DIR}" \
  "${OA_DIR}" \
  "${OA_DIR}/mysql" \
  "${OA_DIR}/redis" \
  "${OA_DIR}/init"

install -m 0644 "${STAGING_DIR}/kodbox-compose.yml" "${KODBOX_DIR}/compose.yml"
printf '%s\n' 'INTRANET_HOST=192.168.1.103' | install -m 0600 /dev/stdin "${KODBOX_DIR}/.env"

install -m 0644 "${STAGING_DIR}/ghy-oa-compose.yml" "${OA_DIR}/compose.yml"
install -m 0600 "${STAGING_DIR}/ghy-oa.env.example" "${OA_DIR}/.env"
root_password="$(openssl rand -hex 24)"
sed -i "s/REPLACE_WITH_A_STRONG_PASSWORD/${root_password}/" "${OA_DIR}/.env"

install -m 0644 "${STAGING_DIR}/ruoyi-vue-pro.sql" "${OA_DIR}/init/ruoyi-vue-pro.sql"

chown -R 999:999 "${OA_DIR}/mysql" "${OA_DIR}/redis"
docker load -i "${IMAGE_ARCHIVE}"

if ! docker network inspect ghy-intranet >/dev/null 2>&1; then
  docker network create ghy-intranet >/dev/null
fi

docker compose --env-file "${KODBOX_DIR}/.env" -f "${KODBOX_DIR}/compose.yml" up -d
docker compose --env-file "${OA_DIR}/.env" -f "${OA_DIR}/compose.yml" up -d mysql redis

for attempt in $(seq 1 60); do
  if docker exec kodbox test -f /var/www/html/app/controller/user/sso.class.php >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "${attempt}" -eq 60 ]]; then
    docker logs kodbox >&2
    exit 1
  fi
done

if docker exec kodbox grep -q 'buildGroupInfo' /var/www/html/app/controller/user/sso.class.php; then
  echo '[KodBox] SSO fields already patched.'
else
  docker cp "${SSO_PATCH_FILE}" kodbox:/tmp/kodbox-sso-fields.patch
  docker exec kodbox sh -c 'patch -p0 < /tmp/kodbox-sso-fields.patch'
  docker restart kodbox >/dev/null
fi

PLUGIN_BASE_DIR="${KODBOX_DIR}/site/plugins" \
  bash "${PLUGIN_SYNC_SCRIPT}"

for attempt in $(seq 1 60); do
  if docker exec ruoyi-mysql sh -c 'mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ "${attempt}" -eq 60 ]]; then
    docker logs ruoyi-mysql >&2
    exit 1
  fi
done

docker compose --env-file "${OA_DIR}/.env" -f "${OA_DIR}/compose.yml" up -d server admin
