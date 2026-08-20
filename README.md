# OpenWiki Server

把 LangChain **OpenWiki**（`langchain-ai/openwiki`，Markdown wiki 内核）封装为独立对外服务的 Wiki 引擎，
供 `/home/open-ikc` 的 Wiki 库能力消费；对外提供 **HTTP / gRPC / Celery / MCP / CLI** 五类接口。

- 设计方案：`docs/解决方案.md`
- gRPC 权威契约：`proto/wiki/v1/wiki.proto`
- 配置样例：`config/engine.example.yaml`（全部可用环境变量覆盖）

## 内核说明

- OpenWiki 为 Node CLI（`npm i openwiki`，项目内 `node_modules/.bin/openwiki`），引擎以子进程方式调用，
  `HOME` 指向 wiki 实例目录实现多租户隔离（`~/.openwiki` 配置与 `~/.openwiki/wiki` 产物均落在实例目录内）。
- **守卫式降级**：openwiki 未安装 / LLM 调用失败 / 无网络时，`build_from_doc` 自动切规则切页
  （`granularity=heading/section/page` + `extractFields` 行抽取），全链路离线可用。
- 稳定 ID 与 open-ikc 完全兼容：`wikiId = wiki_ + sha1(kbId)[:12]`，
  `pageId = wiki_ + sha1(kbId:stableKey)[:12]`，`stableKey = normalize_title(title)`。

## 快速开始

```bash
# 依赖（复用已有 venv；本机可用 semantica-graph-server/.venv）
pip install -e . --no-build-isolation

# 启动 HTTP 服务（默认 18011）
openwiki-server serve http

# CLI 走通全链路（离线规则模式）
export OPENWIKI_SERVER_DATA_DIR=/tmp/ow-demo OPENWIKI_SERVER_OPENWIKI=0
openwiki-server create --kb-id kb_demo --name 演示Wiki \
  --config '{"granularity":"heading","extractFields":["负责人"]}'
openwiki-server build wiki_fb42912a4348 --doc-id doc1 --title 产品手册 \
  --markdown '# 产品手册\n\n## 安装\n\n安装说明。负责人：张三'
openwiki-server tree wiki_fb42912a4348
openwiki-server search wiki_fb42912a4348 --q 安装
openwiki-server stat wiki_fb42912a4348
openwiki-server export wiki_fb42912a4348
```

## Docker 部署（单镜像，含 HAProxy）

参考 `/home/open-ikc` 的单镜像代理拓扑：**Python 引擎 + Node openwiki 内核 + HAProxy 代理层构建到同一镜像**，
引擎进程（uvicorn 18011 / gRPC 50052）只监听容器回环，对外唯一入口为 HAProxy
（HTTP `:8080` 反代 uvicorn、gRPC `:50052` TCP 透传、stats `:8404`）。

```
宿主机 client
  │ http://127.0.0.1:18011   grpc://127.0.0.1:50052   http://127.0.0.1:8404（stats）
  ▼
┌────────────────────────────────────────────────┐
│  容器 openwiki-server-app-1                     │
│  HAProxy(:8080 HTTP / :50052 gRPC / :8404 stats)│
│     │ 反向代理 / TCP 透传                        │
│     ▼                                          │
│  uvicorn(127.0.0.1:18011) + gRPC(127.0.0.1:50052)│
└────────────────────────────────────────────────┘
```

```bash
# 构建镜像（openwiki-server:<package.json version>，含 openwiki 内核与 HAProxy）
bash scripts/build_docker.sh
# 启动（默认入口 http://127.0.0.1:18011；stats http://127.0.0.1:8404）
docker compose up -d
# 启用 Celery worker（redis + worker 一起启动）
docker compose --profile worker up -d
# 冒烟验证（8 项断言，--force-build 可强制重建）
bash scripts/docker_smoke.sh
```

- 镜像内 HAProxy 配置模板 `/etc/haproxy/haproxy.cfg.tmpl` 由入口脚本 envsubst 渲染
  `HAPROXY_STATS_USER / HAPROXY_STATS_PASSWORD`（默认 `admin/change-me`，生产必改）。
- 数据卷 `app_data` 挂载 `/app/data`（SQLite 与 wiki 产物持久化）；worker 与 app 共用同一数据卷。
- 环境变量模板：`cp docker/.env.example .env`（生产密码、端口、LLM 内核配置）。
- `OPENWIKI_SERVER_OPENWIKI=0` 可强制离线规则切页（镜像内已含 Node 22 + openwiki 内核，
  默认启用、LLM 失败自动降级）。

## 五类接口

| 协议面 | 入口 | 说明 |
| --- | --- | --- |
| HTTP | `openwiki-server serve http` | FastAPI，`/api/v1/wiki/*`，envelope 对齐 open-ikc |
| gRPC | `openwiki-server serve grpc` | `wiki.v1.WikiService`，动态 descriptor 实现 |
| Celery | `openwiki-server serve worker` | 任务 `openwiki_server.build / merge / deprecate_doc / export / update / ingest` |
| MCP | `openwiki-server serve mcp` | stdio JSON-RPC，`initialize / tools/list / tools/call` |
| CLI | `openwiki-server ...` | typer，退出码 0/1/6 约定同 open-ikc `ikc` |

## 环境变量

`OPENWIKI_SERVER_DATA_DIR` / `_DB_PATH` / `_HTTP_HOST` / `_HTTP_PORT`（18011）/
`_GRPC_HOST` / `_GRPC_PORT`（50052）/ `_CELERY_BROKER` / `_CELERY_BACKEND` /
`_OPENWIKI_BIN` / `_OPENWIKI`（0 关闭内核）/ `_PROVIDER` / `_MODEL_ID` /
`_UPDATE_TIMEOUT` / `_LOG_LEVEL`；Docker 额外使用 `HAPROXY_STATS_USER` /
`HAPROXY_STATS_PASSWORD`（HAProxy stats 登录）与 `OPENWIKI_HTTP_PORT` /
`OPENWIKI_GRPC_PORT` / `HAPROXY_STATS_PORT`（宿主端口映射）

## 测试

```bash
PYTHONPATH=. python -m pytest tests -q
```

> 沙箱/CI 若禁止绑定 socket，gRPC 真链路测试自动 skip（进程内 handler 语义仍覆盖）。
