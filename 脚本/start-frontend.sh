#!/bin/bash
set -e

# 项目根目录
PROJECT_ROOT="/Users/mac/项目/若伊部署/yudao-ui/yudao-ui-admin-vben-temp"

echo "===== 前端启动脚本 ====="

# 进入项目目录
cd "$PROJECT_ROOT"

LOCAL_ENV_FILE="/Users/mac/项目/若伊部署/脚本/.local-dev.env"
if [ -r "$LOCAL_ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$LOCAL_ENV_FILE"
fi

# 要检查和杀掉的进程关键字
PROCESS_KEYWORDS=("vite" "node.*web-antd")
# 前端端口
FRONTEND_PORT=7700

# 杀掉已启动的前端进程
echo "[1/3] 检查并停止已运行的前端进程..."
for keyword in "${PROCESS_KEYWORDS[@]}"; do
    PIDS=$(ps aux | grep -E "$keyword" | grep -v grep | awk '{print $2}' | sort -rn)
    if [ -n "$PIDS" ]; then
        echo "  发现进程: $PIDS"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        echo "  已停止"
    fi
done

# 检查端口是否被占用
EXISTING_PID=$(lsof -ti :$FRONTEND_PORT 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "[2/3] 端口 $FRONTEND_PORT 被占用，杀掉进程: $EXISTING_PID"
    kill -9 $EXISTING_PID 2>/dev/null || true
    sleep 1
fi

# 启动前端
echo "[3/3] 启动前端 (端口: $FRONTEND_PORT)..."
cd "$PROJECT_ROOT"
VITE_GLOB_FILE_PREVIEW_URL="${OA_FILE_PREVIEW_URL:-}" \
VITE_GLOB_FILE_PREVIEW_FETCH_ORIGIN="${OA_FILE_PREVIEW_FETCH_ORIGIN:-}" \
    nohup pnpm --filter @vben/web-antd dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" > /tmp/yudao-frontend.log 2>&1 &
FRONTEND_PID=$!

echo ""
echo "===== 启动完成 ====="
echo "  前端 PID: $FRONTEND_PID"
echo "  访问地址: http://localhost:$FRONTEND_PORT"
echo "  日志文件: /tmp/yudao-frontend.log"
echo ""
echo "查看日志: tail -f /tmp/yudao-frontend.log"
