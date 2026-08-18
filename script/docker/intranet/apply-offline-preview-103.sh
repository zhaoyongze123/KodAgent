#!/usr/bin/env bash
set -Eeuo pipefail

FRONT_ARCHIVE=${1:?用法：$0 /path/to/oa-frontend-preview-*.tar.gz /path/to/preview-proj.conf}
CONF_SOURCE=${2:?用法：$0 /path/to/oa-frontend-preview-*.tar.gz /path/to/preview-proj.conf}

readonly NGINX_ROOT=/data/proj/nginx
readonly NGINX_HTML="$NGINX_ROOT/html"
readonly NGINX_CONF="$NGINX_ROOT/conf.d/oa-preview.conf"
readonly BACKUP_ROOT=/data/oa-manual/backups/preview
readonly TS=$(date +%Y%m%d-%H%M%S)
readonly BACKUP="$BACKUP_ROOT/$TS"

[[ $EUID -eq 0 ]] || { echo '必须以 root 身份运行' >&2; exit 1; }
[[ -f "$FRONT_ARCHIVE" ]] || { echo "前端包不存在：$FRONT_ARCHIVE" >&2; exit 1; }
[[ -f "$CONF_SOURCE" ]] || { echo "Nginx 配置不存在：$CONF_SOURCE" >&2; exit 1; }
[[ -d "$NGINX_HTML" ]] || { echo "现有前端目录不存在：$NGINX_HTML" >&2; exit 1; }

ARCHIVE_SHA="${FRONT_ARCHIVE}.sha256"
if [[ -f "$ARCHIVE_SHA" ]]; then
    (cd "$(dirname "$ARCHIVE_SHA")" && sha256sum -c "$(basename "$ARCHIVE_SHA")")
fi

install -d -m 0750 "$BACKUP_ROOT" "$BACKUP" /data/oa-manual/update
cp -a "$NGINX_HTML" "$BACKUP/html.before"
cp -a "$NGINX_ROOT/conf.d" "$BACKUP/conf.d.before"
if [[ -f "$NGINX_CONF" ]]; then
    cp -a "$NGINX_CONF" "$BACKUP/oa-preview.conf.before"
fi

stage=$(mktemp -d /data/oa-manual/update/preview-stage.XXXXXX)
tar -xzf "$FRONT_ARCHIVE" -C "$stage" --strip-components=1
[[ -f "$stage/index.html" ]] || { echo '前端包中没有 dist/index.html' >&2; exit 1; }

# Nginx 使用固定 bind mount，不能直接改目录名；先备份，再同步到原目录。
rsync -a --delete "$stage/" "$NGINX_HTML/"
chown -R daiwei:daiwei "$NGINX_HTML"
find "$NGINX_HTML" -type d -exec chmod 0755 {} +
find "$NGINX_HTML" -type f -exec chmod 0644 {} +
install -m 0644 "$CONF_SOURCE" "$NGINX_CONF"

if ! docker exec proj-nginx nginx -t; then
    rsync -a --delete "$BACKUP/html.before/" "$NGINX_HTML/"
    chown -R daiwei:daiwei "$NGINX_HTML"
    find "$NGINX_HTML" -type d -exec chmod 0755 {} +
    find "$NGINX_HTML" -type f -exec chmod 0644 {} +
    if [[ -f "$BACKUP/oa-preview.conf.before" ]]; then
        install -m 0644 "$BACKUP/oa-preview.conf.before" "$NGINX_CONF"
    else
        rm -f "$NGINX_CONF"
    fi
    echo "Nginx 配置检查失败，已恢复前端和配置；备份：$BACKUP" >&2
    exit 1
fi

docker exec proj-nginx nginx -s reload
curl -fsS -o /dev/null -w 'preview_http_status=%{http_code}\n' \
    --max-time 20 http://192.168.1.103:18112/

printf 'preview_deploy_ok\nbackup=%s\nconfig=%s\n' "$BACKUP" "$NGINX_CONF"
