# Docker 部署说明

## 目标

这套脚本用于当前仓库的 OA/BPM 版本进行三套环境管理：

- `dev`：本地开发 / 本机联调
- `stage`：`124.221.4.228` 生产测试环境
- `prod`：未来正式生产环境

规划院内网 OA 另有一套与上述通用 Docker 入口隔离的目标环境配置：
`TARGET_ENV=local|103|production`。其中 `local` 使用 Compose，`103` 和
`production` 保持现有宿主机 JAR + 既有 Nginx 形态，不会被 `deploy.sh` 自动重建。

环境变量入口统一放在：

- `script/docker/env/dev.env`
- `script/docker/env/stage.env`（本机真实 stage 配置，不入库）
- `script/docker/env/prod.env`（本机真实 prod 配置，不入库）
- `script/docker/env/stage.env.example`（stage 模板，入库）
- `script/docker/env/prod.env.example`（prod 模板，入库）

前端构建环境变量统一放在：

- `script/docker/env/frontend.dev.env`
- `script/docker/env/frontend.stage.env`
- `script/docker/env/frontend.prod.env`

当前已验证的 stage 远端目录：

- `/root/deployments/ruoyi-release`

## 本地直接运行

```bash
cd /Users/mac/项目/若伊部署
docker compose --env-file script/docker/env/dev.env -f script/docker/docker-compose.yml up -d --build
```

默认端口：

- 前端：`http://127.0.0.1:18080`
- 后端：`http://127.0.0.1:48080`
- MySQL：`127.0.0.1:13306`
- Redis：`127.0.0.1:16379`

## 手工部署 stage

```bash
cd /Users/mac/项目/若伊部署
cp script/docker/env/stage.env.example script/docker/env/stage.env
# 按实际情况填写密码、微信、小程序等机密项
DEPLOY_ENV=stage bash script/docker/deploy.sh
```

脚本流程：

1. 本地执行 `mvn -pl yudao-server -am clean package -DskipTests`
2. 构建 `ruoyi-server:local` 和 `ruoyi-admin:local`
3. `docker save` 导出镜像 tar
4. 上传到目标环境机器
5. 在远端 `/root/deployments/ruoyi-release` 重载应用
6. 自动清理本地导出包、未使用 Docker 镜像 / 构建缓存，以及服务器上的旧 dangling 镜像
7. 校验 `http://127.0.0.1:48080/actuator/health`

说明：

- `bash script/docker/deploy.sh` 默认读取 `script/docker/env/stage.env`
- 如果 `script/docker/env/stage.env` 不存在，会回退读取 `script/docker/env/stage.env.example`
- 默认是“只更新应用，不覆盖数据库”
- 默认会自动删除本地导出的 tar / SQL 包，并清理本地未使用的 Docker 镜像与 build cache
- 服务器在新镜像启动成功后，也会自动清理旧的 dangling 镜像和上传残留文件
- 如果要做一次全量数据库覆盖，显式执行：

```bash
cd /Users/mac/项目/若伊部署
IMPORT_DATABASE=true bash script/docker/deploy.sh
```

- `bash script/docker/deploy-to-228.sh` 是固定走 `stage` 的快捷入口，并默认 `IMPORT_DATABASE=true`

## 切换环境

切 `stage`：

```bash
cp script/docker/env/stage.env.example script/docker/env/stage.env
DEPLOY_ENV=stage bash script/docker/deploy.sh
```

切 `prod`：

```bash
cp script/docker/env/prod.env.example script/docker/env/prod.env
DEPLOY_ENV=prod bash script/docker/deploy.sh
```

本地起 `dev`：

```bash
docker compose --env-file script/docker/env/dev.env -f script/docker/docker-compose.yml up -d --build
```

## GitHub Actions 自动部署

仓库新增了 `.github/workflows/deploy-stage.yml`，用途是“自动部署 stage 应用镜像，不覆盖数据库”。

注意：

- stage 目标地址是 `124.221.4.228`，GitHub 官方托管 Runner 无法直接访问。
- workflow 必须跑在能访问该内网地址的 `self-hosted runner` 上，并打上 `ruoyi-deploy` 标签。
- workflow 会用 `script/docker/env/stage.env.example` 作为模板，再把 GitHub Secrets 注入成临时 `.stage.ci.env`。
- workflow 最终直接调用 `script/docker/deploy.sh`，和手工部署走同一套逻辑，避免两边漂移。

需要配置的 Secret：

- `DEPLOY_SSH_PRIVATE_KEY`：用于登录 stage 机器的私钥
- `STAGE_MYSQL_ROOT_PASSWORD`
- `STAGE_WX_MP_APP_ID`
- `STAGE_WX_MP_SECRET`
- `STAGE_WX_MINIAPP_APP_ID`
- `STAGE_WX_MINIAPP_SECRET`

## 环境变量覆盖

可通过环境变量覆盖默认值，例如：

```bash
DEPLOY_ENV=stage REMOTE_PASSWORD=000000 bash script/docker/deploy.sh
```

如果临时不想自动清理本地构建产物，可以显式关闭：

```bash
CLEAN_LOCAL_ARTIFACTS=false CLEAN_LOCAL_DOCKER_CACHE=false DEPLOY_ENV=stage bash script/docker/deploy.sh
```

## 维护约定

- `dev` 直接使用已入库的 `dev.env`
- `stage / prod` 只提交 `.env.example` 模板，真实机密保留在部署机或 CI Secret
- 手工部署和 CI 部署统一走 `script/docker/deploy.sh`
- `124.221.4.228` 明确归类为本项目唯一部署服务器

## 规划院三套目标环境

规划院 OA 的本地、103 验证机和正式内网配置集中在 `script/docker/env/targets/`，加载器和校验器分别是：

```bash
source script/docker/env/load-target-env.sh 103
bash script/docker/env/validate-target-env.sh 103
```

详细的 secrets、端口、预览服务和手工 JAR 更新边界见：
`script/docker/目标环境管理说明.md`。
