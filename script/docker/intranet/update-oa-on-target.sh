#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="$(basename "$0")"
# Optional target profile loading keeps the same update script usable on 103 and
# production without copying environment-specific paths into the script.
if [[ -n "${TARGET_ENV:-}" ]]; then
  readonly TARGET_LOADER="$(cd "$(dirname "${BASH_SOURCE[0]}")/../env" && pwd)/load-target-env.sh"
  [[ -f "${TARGET_LOADER}" ]] || { echo "[ERROR] 找不到目标环境加载器：${TARGET_LOADER}" >&2; exit 1; }
  # shellcheck disable=SC1090
  source "${TARGET_LOADER}" "${TARGET_ENV}"
fi

readonly OA_ROOT="${OA_ROOT:-/data/oa-manual}"
readonly UPDATE_ROOT="${UPDATE_ROOT:-${OA_ROOT}/update}"
readonly BACKUP_ROOT="${BACKUP_ROOT:-${OA_ROOT}/backups/updates}"
readonly APP_ROOT="${APP_ROOT:-${OA_ROOT}/app}"
readonly NGINX_ROOT="${NGINX_ROOT:-${OA_NGINX_ROOT:-${OA_ROOT}/nginx}}"
readonly HTML_ROOT="${HTML_ROOT:-${NGINX_ROOT}/html}"
readonly DB_ENV="${DB_ENV:-${OA_DB_ROOT:-${OA_ROOT}/db}/.env}"
readonly DB_CONTAINER="${DB_CONTAINER:-${MYSQL_CONTAINER:-oa-manual-mysql}}"
readonly APP_SERVICE="${APP_SERVICE:-oa-manual.service}"
readonly NGINX_CONTAINER="${NGINX_CONTAINER:-oa-manual-nginx}"
readonly HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:48180/actuator/health}"
readonly FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:18080/}"
readonly LOCK_FILE="${LOCK_FILE:-${UPDATE_ROOT}/.update.lock}"

RELEASE_DIR=""
RELEASE_ID=""
BACKUP_DIR=""
HAS_APP=0
HAS_FRONTEND=0
SQL_FILES=()
SQL_APPLIED=0
APP_CHANGED=0
FRONTEND_CHANGED=0
APP_NEEDS_RESTART=0

usage() {
  cat <<EOF
Usage:
  sudo ${SCRIPT_NAME} check <release-dir>
  sudo ${SCRIPT_NAME} apply <release-dir>
  sudo ${SCRIPT_NAME} rollback <backup-dir>

Release layout:
  app/app.jar              optional backend JAR
  frontend/dist/           optional frontend build output
  sql/*.sql                optional forward-only migrations
  CHANGELOG.md             required release notes
  SHA256SUMS               optional checksum file
  release.env              optional metadata, only RELEASE_ID is read

The script manages the isolated OA installation under ${OA_ROOT}.
It never imports the 103 state snapshot and never modifies KodBox.
EOF
}

die() {
  echo "[ERROR] $*" >&2
  exit 1
}

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || die "请使用 sudo 或 root 执行。"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"
}

safe_release_path() {
  local path="$1"
  [[ -d "$path" ]] || die "更新目录不存在：$path"
  [[ "$path" != / ]] || die "拒绝使用根目录作为更新包。"
  [[ "$path" != "$OA_ROOT" ]] || die "拒绝把 OA 根目录本身作为更新包。"
}

read_release_metadata() {
  RELEASE_ID="$(basename "$RELEASE_DIR")"
  if [[ -f "$RELEASE_DIR/release.env" ]]; then
    local line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%$'\r'}"
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ "$line" =~ ^[[:space:]]*$ ]] && continue
      if [[ "$line" =~ ^[[:space:]]*RELEASE_ID[[:space:]]*=[[:space:]]*([A-Za-z0-9._-]+)[[:space:]]*$ ]]; then
        value="${BASH_REMATCH[1]}"
        RELEASE_ID="$value"
      elif [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*= ]]; then
        key="${BASH_REMATCH[1]}"
        [[ "$key" == "RELEASE_ID" ]] || log "忽略 release.env 未知字段：$key"
      else
        die "release.env 格式错误：$line"
      fi
    done < "$RELEASE_DIR/release.env"
  fi
  [[ "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || die "无效的发布版本标识：$RELEASE_ID"
}

collect_release_files() {
  HAS_APP=0
  HAS_FRONTEND=0
  APP_NEEDS_RESTART=0
  SQL_FILES=()

  [[ -f "$RELEASE_DIR/app/app.jar" ]] && HAS_APP=1
  [[ -d "$RELEASE_DIR/frontend/dist" ]] && HAS_FRONTEND=1

  if [[ -d "$RELEASE_DIR/sql" ]]; then
    while IFS= read -r file; do SQL_FILES+=("$file"); done < <(find "$RELEASE_DIR/sql" -maxdepth 1 -type f -name '*.sql' -print | sort)
  fi
  (( HAS_APP || HAS_FRONTEND || ${#SQL_FILES[@]} )) || die "更新包没有 app.jar、dist 或 SQL。"
  if (( HAS_APP || ${#SQL_FILES[@]} )); then
    APP_NEEDS_RESTART=1
  fi
  if (( HAS_FRONTEND )); then
    [[ -f "$RELEASE_DIR/frontend/dist/index.html" ]] || die "前端 dist 缺少 index.html。"
  fi
}

validate_release() {
  safe_release_path "$RELEASE_DIR"
  [[ -f "$RELEASE_DIR/CHANGELOG.md" ]] || die "更新包缺少 CHANGELOG.md。"
  read_release_metadata
  collect_release_files

  if [[ -f "$RELEASE_DIR/SHA256SUMS" ]]; then
    log "校验更新包 SHA-256。"
    (cd "$RELEASE_DIR" && sha256sum -c SHA256SUMS)
  fi

  local unsafe
  unsafe="$(find "$RELEASE_DIR/sql" -maxdepth 1 -type f \( \
    -name 'ruoyi-vue-pro.sql' -o \
    -name 'install-order.txt' -o \
    -name '*103-state*' \
  \) -print 2>/dev/null || true)"
  [[ -z "$unsafe" ]] || die "更新包包含全量初始化/103 快照文件，已拒绝：$unsafe"

  [[ -f "$DB_ENV" ]] || die "找不到 OA 数据库配置：$DB_ENV"
  [[ -d "$APP_ROOT" ]] || die "找不到 OA 应用目录：$APP_ROOT"
  [[ -d "$HTML_ROOT" ]] || die "找不到 OA 前端目录：$HTML_ROOT"
  docker inspect "$DB_CONTAINER" >/dev/null 2>&1 || die "找不到数据库容器：$DB_CONTAINER"
  docker inspect "$DB_CONTAINER" --format '{{.State.Status}}' | grep -qx running || die "数据库容器未运行：$DB_CONTAINER"
  if (( HAS_FRONTEND )); then
    docker inspect "$NGINX_CONTAINER" >/dev/null 2>&1 || die "找不到 OA Nginx 容器：$NGINX_CONTAINER"
  fi
}

load_db_env() {
  set -a
  # shellcheck disable=SC1090
  . "$DB_ENV"
  set +a
  : "${MYSQL_DATABASE:?${DB_ENV} 未设置 MYSQL_DATABASE}"
  : "${MYSQL_ROOT_PASSWORD:?${DB_ENV} 未设置 MYSQL_ROOT_PASSWORD}"
}

acquire_lock() {
  install -d -m 0750 "$UPDATE_ROOT" "$BACKUP_ROOT"
  exec 9>"$LOCK_FILE"
  flock -n 9 || die "已有另一个 OA 更新正在执行。"
}

backup_current_state() {
  BACKUP_DIR="${BACKUP_ROOT}/${RELEASE_ID}-$(date +%Y%m%d-%H%M%S)"
  install -d -m 0700 "$BACKUP_DIR/app" "$BACKUP_DIR/nginx" "$BACKUP_DIR/db"
  printf '%s\n' "$RELEASE_DIR" > "$BACKUP_DIR/release-dir.txt"
  cp -a "$RELEASE_DIR/CHANGELOG.md" "$BACKUP_DIR/CHANGELOG.md"

  if [[ -f "$APP_ROOT/app.jar" ]]; then
    cp -a "$APP_ROOT/app.jar" "$BACKUP_DIR/app/app.jar"
  fi
  if (( HAS_FRONTEND )); then
    tar -C "$HTML_ROOT" -czf "$BACKUP_DIR/nginx/html-before.tar.gz" .
  fi
  [[ -f "$APP_ROOT/run.sh" ]] && cp -a "$APP_ROOT/run.sh" "$BACKUP_DIR/app/run.sh"
  [[ -f "$APP_ROOT/.env" ]] && cp -a "$APP_ROOT/.env" "$BACKUP_DIR/app/app.env"
  [[ -f "$DB_ENV" ]] && cp -a "$DB_ENV" "$BACKUP_DIR/db/db.env"
  [[ -f "$NGINX_ROOT/conf.d/oa.conf" ]] && cp -a "$NGINX_ROOT/conf.d/oa.conf" "$BACKUP_DIR/nginx/oa.conf"

  log "备份 OA 数据库。"
  docker exec -e MYSQL_PWD="$MYSQL_ROOT_PASSWORD" "$DB_CONTAINER" \
    mysqldump -uroot --single-transaction --routines --triggers "$MYSQL_DATABASE" \
    | tee "$BACKUP_DIR/db/${MYSQL_DATABASE}.sql" >/dev/null
  chmod 0600 "$BACKUP_DIR/db/${MYSQL_DATABASE}.sql"
  log "备份完成：$BACKUP_DIR"
}

apply_sql() {
  local sql
  (( ${#SQL_FILES[@]} )) || return 0
  SQL_APPLIED=1
  for sql in "${SQL_FILES[@]}"; do
    log "执行增量 SQL：$(basename "$sql")"
    docker exec -i -e MYSQL_PWD="$MYSQL_ROOT_PASSWORD" "$DB_CONTAINER" \
      mysql -uroot "$MYSQL_DATABASE" < "$sql"
  done
}

stop_app() {
  (( APP_NEEDS_RESTART )) || return 0
  if systemctl is-active --quiet "$APP_SERVICE"; then
    log "停止 OA 后端：$APP_SERVICE"
    systemctl stop "$APP_SERVICE"
  fi
}

replace_app() {
  (( HAS_APP )) || return 0
  APP_CHANGED=1
  install -m 0644 "$RELEASE_DIR/app/app.jar" "$APP_ROOT/app.jar.new"
  mv -f "$APP_ROOT/app.jar.new" "$APP_ROOT/app.jar"
  chmod 0644 "$APP_ROOT/app.jar"
  log "已替换 OA JAR。"
}

replace_frontend() {
  (( HAS_FRONTEND )) || return 0
  FRONTEND_CHANGED=1
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$RELEASE_DIR/frontend/dist/" "$HTML_ROOT/"
  else
    local stage_dir="${HTML_ROOT}.update.$$"
    rm -rf -- "$stage_dir"
    install -d -m 0755 "$stage_dir"
    cp -a "$RELEASE_DIR/frontend/dist/." "$stage_dir/"
    find "$HTML_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    cp -a "$stage_dir/." "$HTML_ROOT/"
    rm -rf -- "$stage_dir"
  fi
  log "已更新 OA 前端 dist。"
}

reload_nginx_if_needed() {
  (( FRONTEND_CHANGED )) || return 0
  log "校验并重新加载 OA Nginx。"
  docker exec "$NGINX_CONTAINER" nginx -t
  docker exec "$NGINX_CONTAINER" nginx -s reload
}

wait_health() {
  local attempt
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
      log "OA 健康检查通过：$HEALTH_URL"
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_frontend() {
  local attempt
  for attempt in $(seq 1 15); do
    if curl -fsS --max-time 5 "$FRONTEND_URL" -o /dev/null; then
      log "OA 前端检查通过：$FRONTEND_URL"
      return 0
    fi
    sleep 1
  done
  return 1
}

restore_binaries() {
  [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || return 0
  if [[ -f "$BACKUP_DIR/app/app.jar" ]]; then
    cp -a "$BACKUP_DIR/app/app.jar" "$APP_ROOT/app.jar.restore"
    mv -f "$APP_ROOT/app.jar.restore" "$APP_ROOT/app.jar"
  fi
  if (( HAS_FRONTEND )) && [[ -f "$BACKUP_DIR/nginx/html-before.tar.gz" ]]; then
    find "$HTML_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    tar -C "$HTML_ROOT" -xzf "$BACKUP_DIR/nginx/html-before.tar.gz"
    docker exec "$NGINX_CONTAINER" nginx -t && docker exec "$NGINX_CONTAINER" nginx -s reload || true
  fi
}

start_app() {
  (( APP_NEEDS_RESTART )) || return 0
  log "启动 OA 后端：$APP_SERVICE"
  systemctl start "$APP_SERVICE"
  wait_health
}

on_error() {
  local status=$?
  trap - ERR
  echo "[ERROR] OA 更新失败，退出码：$status" >&2
  if (( SQL_APPLIED )); then
    echo "[WARN] 增量 SQL 已执行，脚本不会自动恢复数据库；请使用发布包提供的回滚 SQL 或备份恢复方案。" >&2
  fi
  if (( APP_CHANGED || FRONTEND_CHANGED )); then
    log "尝试恢复已变更的 JAR/前端。"
    restore_binaries || true
  fi
  if (( APP_NEEDS_RESTART )); then
    log "尝试启动 OA 后端：$APP_SERVICE"
    systemctl start "$APP_SERVICE" || true
  fi
  exit "$status"
}

apply_release() {
  validate_release
  load_db_env
  acquire_lock
  backup_current_state
  trap on_error ERR
  stop_app
  apply_sql
  replace_app
  replace_frontend
  reload_nginx_if_needed
  start_app
  if (( HAS_FRONTEND )); then
    wait_frontend
  fi
  ln -sfn "$BACKUP_DIR" "$UPDATE_ROOT/last-success"
  trap - ERR
  log "OA 更新成功：$RELEASE_ID"
  log "数据库、Redis 和 KodBox 未被停止或覆盖。"
}

rollback_release() {
  local backup="$1"
  [[ -d "$backup" ]] || die "备份目录不存在：$backup"
  case "$backup" in
    "$BACKUP_ROOT"/*) ;;
    *) die "回滚目录必须位于：$BACKUP_ROOT" ;;
  esac
  acquire_lock
  local has_app=0
  local has_frontend=0
  if [[ -f "$backup/app/app.jar" ]]; then
    has_app=1
    systemctl stop "$APP_SERVICE" || true
    cp -a "$backup/app/app.jar" "$APP_ROOT/app.jar.restore"
    mv -f "$APP_ROOT/app.jar.restore" "$APP_ROOT/app.jar"
  fi
  if [[ -f "$backup/nginx/html-before.tar.gz" ]]; then
    has_frontend=1
    find "$HTML_ROOT" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    tar -C "$HTML_ROOT" -xzf "$backup/nginx/html-before.tar.gz"
    docker exec "$NGINX_CONTAINER" nginx -t
    docker exec "$NGINX_CONTAINER" nginx -s reload
    wait_frontend || die "回滚后 OA 前端检查未通过。"
  fi
  (( has_app || has_frontend )) || die "备份中没有可回滚的 JAR 或前端文件：$backup"
  if (( has_app )); then
    systemctl start "$APP_SERVICE"
    wait_health || die "回滚后 OA 健康检查未通过。"
  fi
  log "应用/JAR/前端回滚成功：$backup"
  log "数据库未自动回滚；如该版本包含 SQL，请按发布包的回滚方案处理。"
}

main() {
  local command="${1:-}"
  if [[ "$command" == "-h" || "$command" == "--help" || "$command" == "help" ]]; then
    usage
    return 0
  fi

  require_root
  require_command docker
  require_command systemctl
  require_command curl
  require_command flock

  case "$command" in
    check)
      [[ $# -eq 2 ]] || { usage; exit 2; }
      RELEASE_DIR="$2"
      validate_release
      log "更新包检查通过：$RELEASE_ID"
      ;;
    apply)
      [[ $# -eq 2 ]] || { usage; exit 2; }
      RELEASE_DIR="$2"
      apply_release
      ;;
    rollback)
      [[ $# -eq 2 ]] || { usage; exit 2; }
      rollback_release "$2"
      ;;
    *)
      usage
      exit 2
      ;;
  esac
}

main "$@"
