# TeamOS 内网 OA 持续更新操作说明

本说明只用于已部署的规划院 OA。OA 后端是宿主机上的 JAR，由 `oa-manual.service` 管理；前端文件位于 `/data/oa-manual/nginx/html`，由 `oa-manual-nginx` 提供访问。

普通代码更新不停止或重建 MySQL、Redis、Nginx 容器，不修改 KodBox。

## 一、更新包目录

每次发布准备一个独立目录，例如：

```text
oa-update-20260805-01/
├── CHANGELOG.md
├── app/
│   └── app.jar                 # 后端有变化时提供
├── frontend/
│   └── dist/                   # 前端有变化时提供，目录内必须有 index.html
├── sql/                        # 可选，只放本次经审核的前向 SQL，不是初始化基线
│   └── 20260805-001.sql
├── SHA256SUMS                 # 可选
└── release.env                # 可选，仅支持 RELEASE_ID=...
```

更新包不得包含 `frontend/runtime/oa-runtime-config.js`。该文件包含环境地址，
由目标服务器从 `/data/oa-manual/app/.env` 生成，保证同一个更新包可以部署到本地、103 和正式环境。

只改后端时只提供 `app/app.jar`；只改前端时只提供 `frontend/dist/`。不能把全量初始化 SQL、103 快照或 `ruoyi-vue-pro.sql` 放入更新包。首次安装和新环境初始化只使用仓库唯一基线 `sql/mysql/ruoyi-vue-pro.sql`；已有环境如果确实发生结构变化，才在该次发布包中临时提供经过审核、可回滚评估的前向 SQL，发布完成后不把它追加回仓库的初始化目录。

## 二、生成发布文件

后端上传编译后的 JAR，不上传 Java 源码。在项目根目录执行：

```bash
mkdir -p oa-update-20260805-01/app oa-update-20260805-01/frontend/dist
mvn -pl yudao-server -am -DskipTests package
cp yudao-server/target/yudao-server.jar \
  oa-update-20260805-01/app/app.jar
```

前端在 `yudao-ui/yudao-ui-admin-vben-temp` 目录构建：

```bash
cd yudao-ui/yudao-ui-admin-vben-temp
pnpm --filter @vben/web-antd run build
cp -a apps/web-antd/dist/. \
  ../../oa-update-20260805-01/frontend/dist/
cd ../..
```

只改其中一端时，不需要在发布包中放另一端。完成后填写 `CHANGELOG.md`，再上传整个发布目录。

目标服务器需预先配置文件预览地址。例如正式环境执行：

```bash
sudo sh -c 'grep -q "^OA_FILE_PREVIEW_URL=" /data/oa-manual/app/.env \
  && sed -i "s#^OA_FILE_PREVIEW_URL=.*#OA_FILE_PREVIEW_URL=http://192.168.2.10:18112/onlinePreview#" /data/oa-manual/app/.env \
  || printf "\\nOA_FILE_PREVIEW_URL=http://192.168.2.10:18112/onlinePreview\\n" >> /data/oa-manual/app/.env'
```

103 将地址中的主机改为 `192.168.1.103`，本地开发在 `脚本/.local-dev.env` 中配置
`http://127.0.0.1:18112/onlinePreview`。前端代码和更新包无需随环境更换。

## 三、上传更新包

先通过跳转机的 Xshell SFTP 上传到 OA 服务器临时目录：

```text
/home/ssh/oa-upload/update/oa-update-20260805-01/
```

交付包中同时提供了 `oa-update-20260805-01.tar.gz` 及其 `.sha256`。如果上传压缩包，放到 `/home/ssh/oa-upload/update/` 后逐条执行：

```bash
cd /home/ssh/oa-upload/update
sha256sum -c oa-update-20260805-01.tar.gz.sha256
sudo install -d -m 0750 /data/oa-manual/update/incoming
sudo tar -xzf oa-update-20260805-01.tar.gz \
  -C /data/oa-manual/update/incoming
```

解压后，脚本使用的更新目录是：

```text
/data/oa-manual/update/incoming/oa-update-20260805-01/
```

登录 OA 服务器后执行：

```bash
sudo install -d -m 0750 /data/oa-manual/update/incoming
sudo cp -a /home/ssh/oa-upload/update/oa-update-20260805-01 \
  /data/oa-manual/update/incoming/
```

更新脚本放在：

```text
/data/oa-manual/update/update-oa-on-target.sh
```

首次使用时先把 `update-oa-on-target.sh` 上传到 `/home/ssh/oa-upload/update/`，再复制并授权：

```bash
sudo install -d -m 0750 /data/oa-manual/update
sudo install -m 0750 /home/ssh/oa-upload/update/update-oa-on-target.sh \
  /data/oa-manual/update/update-oa-on-target.sh
```

## 四、检查更新包

先检查，不会停止服务、不修改文件：

```bash
sudo bash /data/oa-manual/update/update-oa-on-target.sh \
  check /data/oa-manual/update/incoming/oa-update-20260805-01
```

检查通过后确认发布说明、JAR、前端和 SQL 内容，再执行应用。

## 五、应用更新

```bash
sudo bash /data/oa-manual/update/update-oa-on-target.sh \
  apply /data/oa-manual/update/incoming/oa-update-20260805-01
```

脚本会按发布包内容执行：

```text
1. 使用锁防止并发更新。
2. 备份当前 JAR、前端、配置和 OA 数据库到 /data/oa-manual/backups/updates/。
3. 包含 JAR 或前向 SQL 时停止并重新启动 oa-manual.service。
4. 替换 app.jar；有前向 SQL 时按文件名顺序执行本次发布的 SQL。
5. 有前端时同步 dist，并只 reload oa-manual-nginx。
6. 后端更新检查 `http://127.0.0.1:48180/actuator/health`；前端更新检查 `http://127.0.0.1:18080/`。
```

如果健康检查失败，脚本会尝试恢复旧 JAR 和前端；已经执行的增量 SQL 不会自动逆向，必须按该版本的数据库回滚方案处理。

## 六、查看结果

```bash
sudo systemctl status oa-manual.service --no-pager
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' \
  | grep -E 'oa-manual-(mysql|redis|nginx)'
curl -fsS http://127.0.0.1:48180/actuator/health
curl -I http://127.0.0.1:18080/
```

确认访问地址：

```text
http://192.168.2.10:18080
```

## 七、回滚代码

先列出备份：

```bash
sudo find /data/oa-manual/backups/updates -mindepth 1 -maxdepth 1 \
  -type d -exec basename {} \; | sort
```

指定备份目录执行：

```bash
sudo bash /data/oa-manual/update/update-oa-on-target.sh \
  rollback /data/oa-manual/backups/updates/oa-update-20260805-01-20260805-153000
```

回滚只恢复 JAR 和前端文件，不自动恢复数据库。包含数据库变更的版本，必须同时准备经过审核的回滚 SQL 或使用停机窗口恢复数据库备份。

## 八、更新边界

以下操作不属于普通代码更新，不能用本脚本代替：

```text
MySQL/Redis 镜像或配置升级
Nginx 容器重建
KodBox 插件、SSO 源码修改
103 数据快照导入
```

这些操作需要单独备份、单独变更记录和单独回滚方案。
