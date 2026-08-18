#!/usr/bin/env bash

# LangGraph 本地运行容器的串行启动器。
#
# process-compose 重启一个前台 `docker compose up --force-recreate` 进程时，会先
# 向旧进程发信号、又立即启动新进程。旧 Compose 尚在删除容器而新 Compose 已开始
# 创建同名容器，会触发 Docker 的 "marked for removal" 竞争。本脚本让同一项目的
# Compose 生命周期串行化：旧实例完全退出并释放锁后，新实例才可开始强制重建。

set -euo pipefail

runtime_dir="${TMPDIR:-/tmp}/kodagent-langgraph-compose.lock"
compose_pid=""

release_lock() {
  rm -f "$runtime_dir/pid"
  rmdir "$runtime_dir" 2>/dev/null || true
}

acquire_lock() {
  while ! mkdir "$runtime_dir" 2>/dev/null; do
    local holder_pid=""
    if [[ -f "$runtime_dir/pid" ]]; then
      holder_pid="$(<"$runtime_dir/pid")"
    fi
    # 进程被强制终止时可能留下锁目录；只清理已确认不存活的精确 PID 锁。
    if [[ "$holder_pid" =~ ^[0-9]+$ ]] && ! kill -0 "$holder_pid" 2>/dev/null; then
      rm -f "$runtime_dir/pid"
      rmdir "$runtime_dir" 2>/dev/null || true
      continue
    fi
    sleep 0.2
  done
  printf '%s\n' "$$" > "$runtime_dir/pid"
}

stop_compose() {
  if [[ -n "$compose_pid" ]] && kill -0 "$compose_pid" 2>/dev/null; then
    kill -TERM "$compose_pid" 2>/dev/null || true
    wait "$compose_pid" || true
  fi
  compose_pid=""
  release_lock
  trap - EXIT
  exit 0
}

trap stop_compose INT TERM HUP
trap release_lock EXIT

acquire_lock
docker compose -f docker-compose.dev.yml up --force-recreate --no-color langgraph-api runtime-outbox &
compose_pid="$!"
wait "$compose_pid"
