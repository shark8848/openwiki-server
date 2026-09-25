# OpenWiki Server 离线镜像部署手册

适用于：**无法直接访问外网拉取镜像/构建镜像**的目标服务器。流程：本机 `docker save` → 手工传输（scp / rsync / U 盘）→ 目标机 `docker load` → `docker compose up -d --no-build`。

参考：PyUploadX 同款离线发布流程（`../pyuploadx/docs/deploy-offline.md`）。

## 0. 一键发布 / 一键部署（推荐）

本机执行一次脚本即可完成“构建 → 导出 → 打包 →（可选）推送远端并拉起服务”：

```bash
cd /home/sharkyai/openwiki-server
# 仅构建 + 导出 + 打包（产物在 docker/images/，可 scp/rsync/U 盘线下传输）
bash scripts/publish-offline.sh --build

# 构建 + 打包 + 推送到远端并 ssh 一键 load/compose up（需免密登录）
REMOTE_HOST=10.88.155.31 bash scripts/publish-offline.sh --build --push
```

产物与校验：

```text
docker/images/ikc-openwiki-server_1.0.0.tar       # 镜像 tar（docker load -i）
docker/images/openwiki-server-compose-1.0.0.tgz   # 部署配置包（compose + env 模板 + 手册 + 远端脚本）
docker/images/openwiki-server-1.0.0-SHA256SUMS.txt# sha256 校验清单
```

远端可选参数：`REMOTE_USER`（默认 root）/ `REMOTE_DIR`（默认 `/opt/openwiki-server`）/ `SSH_PORT` / `TRANSFER=scp`，
可写入 `config/remote.env` 固化。目标服务器侧的等价手动命令见第 3/4 节。

## 1. 镜像清单（单节点模式）

| 镜像:标签 | 大小 | 来源 | 用途 |
| --- | --- | --- | --- |
| `ikc-openwiki-server:1.0.0` | 磁盘约 1.17 GB（导出 tar 约 227 MB） | `Dockerfile` 单阶段 | 单镜像内含 Python 引擎（HTTP/gRPC/Celery/MCP/CLI 五面接口）+ Node `openwiki` 内核 + HAProxy 代理层 |

容器内拓扑（引擎只监听回环，对外唯一入口为 HAProxy）：

```
client -> HAProxy(:8080 HTTP / :50052 gRPC / :8404 stats)
           -> uvicorn(127.0.0.1:18011，仅回环)
           -> gRPC(127.0.0.1:50052，仅回环)
```

> **数据一律外部挂载，不进镜像**：`/app/data`（SQLite `engine.db` + `wikis/` 页面数据）由 compose 命名卷 `openwiki-server_app_data` 持久化；删除/重建容器不丢数据。

## 2. 本机导出

### 2.0 一键构建 + 导出（推荐）

```bash
cd /home/sharkyai/openwiki-server
bash scripts/build_docker.sh --export
# 产物：docker/images/ikc-openwiki-server_1.0.0.tar
```

镜像已内置 `openwiki-server`（引擎 0.3.4）与 `ikc-log-center`（log-center extra），支持 IKC Log Center 远程日志投递（见第 7 节）。

### 2.1 手动导出（复用已有镜像）

```bash
cd /home/sharkyai/openwiki-server
mkdir -p docker/images
docker save -o docker/images/ikc-openwiki-server_1.0.0.tar ikc-openwiki-server:1.0.0
```

### 2.2 部署配置打包（镜像之外还需要 compose/配置）

一键打包（推荐，等价于 `publish-offline.sh` 的 bundle 阶段）：

```bash
cd /home/sharkyai/openwiki-server
tar czf docker/images/openwiki-server-compose-1.0.0.tgz \
  docker-compose.yml \
  config/engine.example.yaml \
  config/env.remote.example \
  docs/deploy-offline.md \
  scripts/deploy-remote.sh
cd docker/images && sha256sum ikc-openwiki-server_1.0.0.tar openwiki-server-compose-1.0.0.tgz \
  > openwiki-server-1.0.0-SHA256SUMS.txt
```

## 3. 传输到目标服务器

```bash
# 示例（scp），或使用 rsync / U 盘
scp docker/images/ikc-openwiki-server_1.0.0.tar \
    docker/images/openwiki-server-compose-1.0.0.tgz \
    docker/images/openwiki-server-1.0.0-SHA256SUMS.txt \
    root@SERVER:/opt/openwiki-server/_release/
```

## 4. 目标服务器导入

```bash
mkdir -p /opt/openwiki-server && cd /opt/openwiki-server
tar xzf _release/openwiki-server-compose-1.0.0.tgz
cd _release && sha256sum -c openwiki-server-1.0.0-SHA256SUMS.txt && cd ..

# 导入镜像（目标机无需 Dockerfile / 构建依赖）
docker load -i _release/ikc-openwiki-server_1.0.0.tar

# 或一键（load + compose up --no-build + 健康检查；首次自动生成 .env）
bash scripts/deploy-remote.sh --release-dir _release

# 校验：与第 1 节清单一致
docker images | grep openwiki-server
docker compose config --images
```

## 5. 配置 `.env`

在 `/opt/openwiki-server/.env` 创建（`docker compose` 自动读取；未设置的项走 compose 内默认值）：

```bash
cd /opt/openwiki-server
cat > .env <<'ENVFILE'
# 宿主端口映射（HAProxy 入口；引擎 18011/50052 只在容器回环，不对外）
OPENWIKI_HTTP_PORT=18011
OPENWIKI_GRPC_PORT=50052
HAPROXY_STATS_PORT=8404
# HAProxy stats 登录（生产必改）
HAPROXY_STATS_USER=admin
HAPROXY_STATS_PASSWORD=change-me

# 运行数据（compose 默认 /app/data 挂载命名卷，一般无需改；
# 若改为主机目录，需 chown 1000:1000 保证容器内可写）
# OPENWIKI_SERVER_DATA_DIR=/app/data
# 日志级别：DEBUG / INFO / WARNING / ERROR
OPENWIKI_SERVER_LOG_LEVEL=INFO

# openwiki 内核与 LLM（1 启用 LLM 合成；0 强制离线规则模式，无需凭据）
OPENWIKI_SERVER_OPENWIKI=1
OPENWIKI_SERVER_PROVIDER=openai-compatible
OPENWIKI_SERVER_MODEL_ID=deepseek-v4-flash
OPENWIKI_SERVER_UPDATE_TIMEOUT=600
# 经本机 litellm 代理（LiteLLM 统一鉴权，key 用 LITELLM_MASTER_KEY；默认走 /v1/chat/completions）
OPENAI_COMPATIBLE_API_KEY=REPLACE_WITH_LITELLM_MASTER_KEY
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:4000/v1
# 直连 DeepSeek 官方端点（不经 litellm）时：
# OPENAI_COMPATIBLE_API_KEY=sk-xxx
# OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com/v1
# 其它 provider 示例：
# OPENAI_API_KEY=xxx                      # provider=openai（可配 OPENAI_BASE_URL）
# ANTHROPIC_API_KEY=xxx                   # provider=anthropic
# GEMINI_API_KEY=xxx                      # provider=gemini
# OPENROUTER_API_KEY=xxx                  # provider=openrouter

# IKC Log Center 远程日志投递（镜像已内置 SDK；不需要则保持 0）
OPENWIKI_SERVER_LOG_CENTER_ENABLED=0
OPENWIKI_SERVER_LOG_CENTER_URL=http://log-center:9315
OPENWIKI_SERVER_LOG_CENTER_TOKEN=

# Celery worker（仅启用 worker 时需要；默认连宿主 6379）
# OPENWIKI_SERVER_CELERY_BROKER=redis://host.docker.internal:6379/0
# OPENWIKI_SERVER_CELERY_BACKEND=redis://host.docker.internal:6379/0
ENVFILE
```

## 6. 启动与验证

```bash
cd /opt/openwiki-server
docker compose up -d --no-build

# 健康检查（端到端：HAProxy -> uvicorn 127.0.0.1:18011）
curl -s http://127.0.0.1:18011/health
# {"status":"ok","service":"openwiki-server"}
curl -s http://127.0.0.1:18011/ready
# {"status":"ready"}

# API 冒烟：创建 wiki 实例
curl -s -X POST http://127.0.0.1:18011/api/v1/wiki/wikis \
  -H 'Content-Type: application/json' \
  -d '{"kbId":"kb-demo","name":"demo","tenantId":"t-1","ownerId":"u-1"}'
# {"traceId":"...","errCode":0,"errMsg":"","data":{...}}

curl -s 'http://127.0.0.1:18011/api/v1/wiki/wikis?tenantId=t-1'

# 触发 LLM 合成刷新（需第 5 节 LLM 凭据正确；凭据缺失/无效时 errCode=500，errMsg 含 openwiki 报错）
curl -s -X POST http://127.0.0.1:18011/api/v1/wiki/wikis/<wikiId>/update \
  -H 'Content-Type: application/json' \
  -d '{"message":"按源文档重新合成"}'

# 故障排查：若返回 504 Gateway Time-out，是 HAProxy 默认 timeout server 60s 掐断长 LLM 请求
# （旧镜像）；新版镜像已内置 timeout server 600s，需重新 load 最新 tar 并重建容器。
# 也可改用异步 job（需 worker + redis）：build/update 带 "async": true，再轮询 /api/v1/wiki/jobs/{jobId}

# HAProxy stats（需第 5 节账号）
curl -s -u admin:change-me http://127.0.0.1:8404/stats | head -5

docker compose ps
```

## 7. 启用 IKC Log Center 远程日志（可选）

镜像内置 `openwiki-server 0.3.0[log-center]`，启用后日志模块启动时自动挂载 `HttpLogHandler`，批量 POST 到 `{url}/ingest`（Bearer token）：

```bash
cd /opt/openwiki-server
sed -i 's/OPENWIKI_SERVER_LOG_CENTER_ENABLED=0/OPENWIKI_SERVER_LOG_CENTER_ENABLED=1/' .env
docker compose up -d --no-build   # 重建容器使新 env 生效

# 验证：容器日志出现挂载成功记录
docker compose logs -f app | grep 'log center'
# {"ts":"...","level":"INFO","logger":"openwiki_engine.logging_setup","message":"log center HTTP 投递已挂载","endpoint":"http://log-center:9315"}

# 目标 log-center 侧：应持续收到 JSON 日志（ts/level/logger/message/request_id/trace_id/node_id）
```

- 未安装/未配置 url 时仅告警降级，不影响服务运行。
- `OPENWIKI_SERVER_LOG_CENTER_TOKEN` 为空时不带 Authorization；需鉴权时填 log-center 下发的 token。

## 8. 非 compose 部署（手动 docker run）

目标机没有 compose 插件、或想完全手动控制时，直接 `docker run` 启动（参考 PyUploadX
离线手册「独立模式」章节）。镜像入口 `openwiki-entrypoint.sh [api|worker]`，默认角色
`api`；不传参数也可用 `-e OPENWIKI_SERVER_ROLE=api|worker` 指定。

### 8.1 前置条件与端口

- 镜像已 `docker load`（见 §4）；宿主目录 `/opt/openwiki-server/data` 挂载为容器
  `/app/data`（SQLite `engine.db` + `wikis/`），删除/重建容器不丢数据。
  **容器以 uid 1000（appuser）运行，宿主数据目录必须可写**，否则启动报
  `sqlite3.OperationalError: unable to open database file`：
  `sudo chown -R 1000:1000 /opt/openwiki-server/data`
- Linux 上经 `host.docker.internal` 访问宿主机服务，必须加
  `--add-host host.docker.internal:host-gateway`。
- 端口（容器端口固定，宿主端口可改；冲突检查：`ss -ltnp | grep -E ':(18011|50052|8404)\b'`）：

| 宿主端口 | 容器端口 | 用途 |
| --- | --- | --- |
| `18011` | `8080` | HTTP API（HAProxy） |
| `50052` | `50052` | gRPC（HAProxy TCP 透传） |
| `8404` | `8404` | HAProxy stats |

### 8.2 环境变量文件 `.env`（`--env-file` 不解析 `${}`，需填具体值）

```bash
mkdir -p /opt/openwiki-server/data
sudo chown -R 1000:1000 /opt/openwiki-server/data   # 容器内 appuser(uid 1000) 需可写
cat > /opt/openwiki-server/.env <<'EOF'
OPENWIKI_SERVER_OPENWIKI=1
OPENWIKI_SERVER_PROVIDER=openai-compatible
OPENWIKI_SERVER_MODEL_ID=deepseek-v4-flash
OPENWIKI_SERVER_UPDATE_TIMEOUT=600
OPENAI_COMPATIBLE_API_KEY=REPLACE_WITH_LITELLM_MASTER_KEY
OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:4000/v1
OPENWIKI_SERVER_LOG_LEVEL=INFO
HAPROXY_STATS_USER=admin
HAPROXY_STATS_PASSWORD=change-me
OPENWIKI_SERVER_LOG_CENTER_ENABLED=0
OPENWIKI_SERVER_LOG_CENTER_URL=http://host.docker.internal:9315
OPENWIKI_SERVER_LOG_CENTER_TOKEN=
OPENWIKI_SERVER_CELERY_BROKER=redis://host.docker.internal:6379/0
OPENWIKI_SERVER_CELERY_BACKEND=redis://host.docker.internal:6379/0
EOF
```

### 8.3 API 容器（默认角色）

```bash
docker run -d --name openwiki-server --restart unless-stopped \
  --add-host host.docker.internal:host-gateway \
  -v /opt/openwiki-server/data:/app/data \
  --env-file /opt/openwiki-server/.env \
  -p 18011:8080 -p 50052:50052 -p 8404:8404 \
  ikc-openwiki-server:1.0.0
```

### 8.4 Worker 容器（可选，需外部 Redis）

与 API 共用同一数据目录（同一 SQLite 引擎数据）：

```bash
docker run -d --name openwiki-server-worker --restart unless-stopped \
  --add-host host.docker.internal:host-gateway \
  -v /opt/openwiki-server/data:/app/data \
  --env-file /opt/openwiki-server/.env \
  ikc-openwiki-server:1.0.0 worker
```

> worker 与 api 必须挂载同一数据目录，且 broker/backend 可达（默认连宿主 6379，
> 非本机时改 `.env` 为实际地址，如 `redis://:密码@192.168.1.20:6379/0`）。

### 8.5 验证与访问

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
curl -s http://127.0.0.1:18011/health && echo
curl -s -X POST http://127.0.0.1:18011/api/v1/wiki/wikis \
  -H 'Content-Type: application/json' \
  -d '{"kbId":"kb-demo","name":"demo","tenantId":"t-1"}'
curl -s -u admin:change-me http://127.0.0.1:8404/stats | head -5
```

- API：`http://<服务器IP>:18011`；gRPC：`<服务器IP>:50052`；stats：`http://<服务器IP>:8404`。

### 8.6 运维与升级

```bash
docker stop openwiki-server openwiki-server-worker
docker start openwiki-server openwiki-server-worker
docker restart openwiki-server openwiki-server-worker

# 升级：docker load 新镜像 → 删旧容器 → 重新 run（数据在宿主目录，不丢）
docker rm -f openwiki-server openwiki-server-worker
docker load -i ikc-openwiki-server_1.0.0.tar
# 再执行 8.3 / 8.4 的 docker run

# 清理（不影响数据）
docker rm -f openwiki-server openwiki-server-worker
```

- 数据备份：`docker run --rm -v /opt/openwiki-server/data:/data -v $(pwd):/backup alpine tar czf /backup/openwiki-data.tgz -C /data .`

## 9. 可选：Celery worker（compose 方式）

需要外部 Redis（broker/backend，默认 `redis://host.docker.internal:6379/0`，可用 `.env` 覆盖）：

（非 compose 方式见 §8.4）

```bash
cd /opt/openwiki-server
docker compose --profile worker up -d --no-build
docker compose ps   # app + worker 均 running
```

## 10. 升级

```bash
# 本机：改代码后重新构建并导出
cd /home/sharkyai/openwiki-server
bash scripts/build_docker.sh --export

# 传输新 tar → 目标机导入 → 重建
# compose 方式：数据在命名卷，重建不丢；非 compose 方式见 §8.6
scp docker/images/ikc-openwiki-server_1.0.0.tar root@SERVER:/opt/openwiki-server/
ssh root@SERVER 'cd /opt/openwiki-server && docker load -i ikc-openwiki-server_1.0.0.tar && docker compose up -d --no-build'
```

## 11. 常用运维

- 查看日志：`docker compose logs -f app`
- 停止：`docker compose down`（数据卷保留；`down -v` 会删除数据，慎用）
- 数据备份（SQLite 引擎数据）：`docker run --rm -v openwiki-server_app_data:/data -v $(pwd):/backup alpine tar czf /backup/openwiki-data.tgz -C /data .`
- 健康检查：`curl -s http://127.0.0.1:18011/health`；`docker compose ps`
