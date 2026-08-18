#!/bin/bash

# RuoYi-Vue-Pro 工作流版本快速启动脚本
# 用法：bash 快速启动.sh [backend|frontend|all]

set -e

PROJECT_ROOT="/Users/mac/项目/若伊部署"
BACKEND_DIR="$PROJECT_ROOT"
FRONTEND_DIR="$PROJECT_ROOT/yudao-ui/yudao-ui-admin-vben-temp"
ENV_FILE="$PROJECT_ROOT/脚本/.local-dev.env"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_separator() {
    echo "═══════════════════════════════════════════════════════════════"
}

show_help() {
    echo "RuoYi-Vue-Pro 工作流版本快速启动脚本"
    echo ""
    echo "用法: bash 快速启动.sh [command]"
    echo ""
    echo "命令:"
    echo "  backend         - 启动后端服务 (编译 + 运行)"
    echo "  frontend        - 启动前端服务"
    echo "  all             - 同时启动后端和前端"
    echo "  help            - 显示此帮助信息"
    echo ""
}

check_dependencies() {
    print_info "检查依赖..."

    if ! command -v java &> /dev/null; then
        print_error "未找到 Java，请先安装 JDK 1.8 或更高版本"
        exit 1
    fi
    print_success "Java 已安装"

    if ! command -v mvn &> /dev/null; then
        print_error "未找到 Maven，请先安装 Maven 3.6.0 或更高版本"
        exit 1
    fi
    print_success "Maven 已安装"

    if [[ "$1" == "frontend" || "$1" == "all" ]]; then
        if ! command -v node &> /dev/null; then
            print_error "未找到 Node.js，请先安装 Node.js 20.0 或更高版本"
            exit 1
        fi
        print_success "Node.js 已安装"
        if ! command -v pnpm &> /dev/null; then
            print_error "未找到 pnpm，请先安装 pnpm 10 或更高版本"
            exit 1
        fi
        print_success "pnpm 已安装"
    fi
}

start_backend() {
    print_separator
    print_info "启动后端服务..."
    print_separator

    cd "$BACKEND_DIR"

    if [ ! -r "$ENV_FILE" ]; then
        print_error "缺少本地开发配置: $ENV_FILE"
        print_info "请先执行: cp 脚本/.local-dev.env.example 脚本/.local-dev.env"
        exit 1
    fi
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a

    print_info "刷新 Maven 依赖..."
    mvn clean install -DskipTests -q
    print_success "Maven 依赖已更新"

    print_info "安装当前工作区后端模块..."
    mvn -pl yudao-server -am install -DskipTests -q
    print_success "后端模块已更新"

    print_separator
    print_info "启动 Spring Boot 应用..."
    print_info "后端地址: http://localhost:7800"
    print_info "API 文档: http://localhost:7800/doc.html"
    print_info "默认用户: admin"
    print_info "默认密码: admin123"
    print_separator

    cd "$BACKEND_DIR"
    mvn -pl yudao-server spring-boot:run \
        -Dspring-boot.run.profiles="${SPRING_PROFILES_ACTIVE:-local}" \
        -Dspring-boot.run.arguments="--server.address=${SERVER_ADDRESS:-127.0.0.1} --server.port=7800"
}

start_frontend() {
    print_separator
    print_info "启动前端服务..."
    print_separator

    if [ ! -d "$FRONTEND_DIR" ]; then
        print_error "前端目录不存在: $FRONTEND_DIR"
        exit 1
    fi

    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ]; then
        print_info "安装 pnpm 依赖..."
        pnpm install
        print_success "依赖安装成功"
    else
        print_success "依赖已存在"
    fi

    print_separator
    print_info "启动前端开发服务..."
    print_info "前端地址: http://localhost:7700"
    print_info "后端 API: http://localhost:7800"
    print_separator

    pnpm --filter @vben/web-antd dev -- --host 0.0.0.0 --port 7700
}

main() {
    print_separator
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║   RuoYi-Vue-Pro 工作流版本快速启动                           ║"
    echo "║   基于完整版删除不必要模块的精简迁移版本                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    print_separator
    echo ""

    if [ -z "$1" ]; then
        show_help
        exit 0
    fi

    case "$1" in
        backend)
            check_dependencies backend
            start_backend
            ;;
        frontend)
            check_dependencies frontend
            start_frontend
            ;;
        all)
            check_dependencies all
            print_info "启动所有服务..."
            start_backend &
            BACKEND_PID=$!
            sleep 10
            start_frontend
            ;;
        help)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
