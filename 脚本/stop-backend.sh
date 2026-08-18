#!/bin/bash
set -e

# 后端端口
BACKEND_PORT=7800

echo "===== 后端进程检查脚本 ====="

# 查找占用端口的进程
echo "[1/2] 检查端口 $BACKEND_PORT 是否被占用..."
PID=$(lsof -ti :$BACKEND_PORT 2>/dev/null || true)

if [ -n "$PID" ]; then
    echo "  端口被占用，进程 PID: $PID"
    echo "  正在停止进程..."
    kill -9 $PID 2>/dev/null || true
    sleep 1

    # 验证是否已停止
    if lsof -ti :$BACKEND_PORT 2>/dev/null; then
        echo "  [失败] 进程仍在运行"
        exit 1
    else
        echo "  [成功] 进程已停止"
    fi
else
    echo "  端口未被占用，无需操作"
fi

# 检查是否有残留的java后端进程
echo "[2/2] 检查残留的 Java 后端进程..."
JAVA_PIDS=$(ps aux | grep "yudao" | grep -E "java.*7800|admin-api" | grep -v grep | awk '{print $2}' | sort -u || true)

if [ -n "$JAVA_PIDS" ]; then
    echo "  发现残留进程: $JAVA_PIDS"
    echo "$JAVA_PIDS" | xargs kill -9 2>/dev/null || true
    echo "  已停止"
else
    echo "  无残留进程"
fi

echo ""
echo "===== 检查完成 ====="
