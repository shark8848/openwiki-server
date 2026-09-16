# OpenWiki Server

把 LangChain **OpenWiki**（`langchain-ai/openwiki`，Markdown wiki 内核）封装为独立对外服务的 Wiki 引擎，
供 `/home/open-ikc` 的 Wiki 库能力消费；对外提供 **HTTP / gRPC / Celery / MCP / CLI** 五类接口。

<p align="center">
  <a href="https://pypi.org/project/openwiki-server/"><img src="https://img.shields.io/pypi/v/openwiki-server" alt="PyPI" /></a>
  <a href="https://pypi.org/project/openwiki-server-sdk/"><img src="https://img.shields.io/pypi/v/openwiki-server-sdk" alt="SDK PyPI" /></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+" />
</p>

- 设计方案：`docs/解决方案.md`
- 离线镜像部署手册：`docs/deploy-offline.md`（docker save → 传输 → load → compose 启动）
- gRPC 权威契约：`proto/wiki/v1/wiki.proto`
- 配置样例：`config/engine.example.yaml`（全部可用环境变量覆盖）
- 命令行测试与调用指南：`docs/命令行测试与调用指南.md`（五类接口全部命令，已用仓库真实文档实测）
- 独立承载服务与 SDK 集成设计：`docs/独立承载服务与SDK集成设计.md`（应用侧快速集成）

## 安装（PyPI）

```bash
pip install openwiki-server                        # 引擎 + 独立承载服务（HTTP/gRPC/Celery/MCP/CLI）
pip install openwiki-server[server]                # + 承载服务依赖
pip install openwiki-server[all]                   # 全部依赖
pip install openwiki-server-sdk                    # 仅应用集成 SDK（httpx，应用侧集成）
```

引擎与独立承载服务发布为 `openwiki-server`，应用集成 SDK 独立发布为
`openwiki-server-sdk`（仅依赖 `httpx`）。SDK 快速开始见
[`sdk/python/README.md`](sdk/python/README.md)。

发布到 PyPI：

```bash
cp config/pypi.env.example config/pypi.env   # 填入 OPENWIKI_PYPI_TOKEN
./scripts/publish-pypi.sh                    # 构建 + 上传
./scripts/publish-pypi.sh --test             # 上传到 TestPyPI
```

## 内核说明

- OpenWiki 为 Node CLI（`npm i openwiki`，项目内 `node_modules/.bin/openwiki`），引擎以子进程方式调用，
  `HOME` 指向 wiki 实例目录实现多租户隔离（`~/.openwiki` 配置与 `~/.openwiki/wiki` 产物均落在实例目录内）。
- **守卫式降级**：openwiki 未安装 / LLM 调用失败 / 无网络时，`build_from_doc` 自动切规则切页
  （`granularity=heading/section/page` + `extractFields` 行抽取），全链路离线可用。
- 稳定 ID 与 open-ikc 完全兼容：`wikiId = wiki_ + sha1(kbId)[:12]`，
  `pageId = wiki_ + sha1(kbId:stableKey)[:12]`，`stableKey = normalize_title(title)`。

## 快速开始

```bash
# 依赖：本仓自带 venv（**不要**复用别的仓库的 venv——对方解释器可能缺 redis-py，
# 会让 HTTP/worker 的 celery 投递静默失败，作业只登记不投递、永远停在 pending）
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[server,dev]'      # 含 HTTP/worker 全部依赖 + 队列依赖组（见「安装」小节的强制契约三条）

# 启动 HTTP 服务（默认 18011）
.venv/bin/openwiki-server serve http

# 异步任务：另起一个进程跑 worker（broker/backend 见 OPENWIKI_SERVER_CELERY_BROKER）
.venv/bin/openwiki-server serve worker

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
│  容器 openwiki-server                          │
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
# 启用 Celery worker（broker/backend 用外部 redis，默认 redis://host.docker.internal:6379/0）
docker compose --profile worker up -d
# 冒烟验证（7 项断言，--force-build 可强制重建）
bash scripts/docker_smoke.sh
```

- 镜像内 HAProxy 配置模板 `/etc/haproxy/haproxy.cfg.tmpl` 由入口脚本 envsubst 渲染
  `HAPROXY_STATS_USER / HAPROXY_STATS_PASSWORD`（默认 `admin/change-me`，生产必改）。
- 数据卷 `app_data` 挂载 `/app/data`（SQLite 与 wiki 产物持久化）；worker 与 app 共用同一数据卷。
- 环境变量模板：`cp docker/.env.example .env`（生产密码、端口、LLM 内核配置）。
- Celery 使用**外部 redis**（compose 不再内置 redis 服务）；默认指向宿主机
  `host.docker.internal:6379`，远程实例在 `.env` 用 `OPENWIKI_SERVER_CELERY_BROKER` /
  `OPENWIKI_SERVER_CELERY_BACKEND` 覆盖；本机 redis 若需密码写成
  `redis://:<密码>@host.docker.internal:6379/0`（未启用 worker 时 app 不主动连接）。
- `OPENWIKI_SERVER_OPENWIKI=0` 可强制离线规则切页（镜像内已含 Node 22 + openwiki 内核，
  默认启用、LLM 失败自动降级）。
- 异步加工：build/merge 等请求带 `async=1` 时登记为 job 并经 Celery 投递（broker 不可达/未配时
  保持 `pending`，可调 `POST /api/v1/wiki/jobs/{job_id}/run` 手动执行；轮询
  `GET /api/v1/wiki/jobs/{job_id}` 查看结果）。任务终态由 `celery_app._run_job` 统一回写：
  成功 `success` + `result`，**失败 `failed` + `error`**（异常仍向上抛，Celery 保持 FAILURE 语义）——
  只在成功时回写会让失败作业永远停在 `pending`，调用方只能靠轮询超时猜。
  注意 HTTP 进程与 worker 必须用**同一套能连 broker 的解释器**：缺 `redis-py` 时 `send_task`
  直接失败，作业只登记不投递（日志 `未投递到 broker`）。

## 五类接口

| 协议面 | 入口 | 说明 |
| --- | --- | --- |
| HTTP | `openwiki-server serve http` | FastAPI，`/api/v1/wiki/*`，envelope 对齐 open-ikc |
| gRPC | `openwiki-server serve grpc` | `wiki.v1.WikiService`，动态 descriptor 实现 |
| Celery | `openwiki-server serve worker` | 任务 `openwiki_server.build / merge / deprecate_doc / export / update / ingest` |
| MCP | `openwiki-server serve mcp` | stdio JSON-RPC，`initialize / tools/list / tools/call` |
| CLI | `openwiki-server ...` | typer，退出码 0/1/6 约定同 open-ikc `ikc` |

## SDK（应用侧快速集成）

openwiki-server 可作**独立承载服务**（本地进程或 Docker 单镜像栈），应用侧用
`openwiki-server-sdk`（参考 open-ikc `open-ikc-sdk` 定义）快速接入全部 wiki 能力：

```bash
pip install openwiki-server-sdk
```

```python
from openwiki_server_sdk import OpenWikiServerClient

with OpenWikiServerClient(base_url="http://127.0.0.1:18011") as client:
    wiki = client.wikis.create(kbId="kb_demo", name="产品知识库",
                               wikiConfig={"granularity": "heading"})
    result = client.wikis.build(
        wiki.wikiId, docId="doc_1", title="产品手册",
        markdown=open("docs/进展.md", encoding="utf-8").read())
    print(result.mode, result.total)
    hits = client.wikis.search(wiki.wikiId, q="HAProxy")
    job = client.wikis.build(wiki.wikiId, docId="doc_2", title="异步", async_=True)
    print(client.jobs.run(job.jobId).status)
```

- 领域方法：`client.wikis.create/list/get/delete/tree/page/search/stat/export/
  build/merge/deprecate_doc/update/ingest` 与 `client.jobs.run/get/list`；
  同步 `OpenWikiServerClient` / 异步 `AsyncOpenWikiServerClient` 共享同一套模型。
- 环境变量引导：`OPENWIKI_SERVER_BASE_URL`（默认 `http://127.0.0.1:18011`）/
  `OPENWIKI_SERVER_TOKEN` / `OPENWIKI_SERVER_USER_ID` / `OPENWIKI_SERVER_TENANT_ID` /
  `OPENWIKI_SERVER_ROLES`，经 `client_from_env()` 构造。
- 自测与冒烟：`cd sdk/python && PYTHONPATH=. python -m pytest tests -q`（36 例 MockTransport）；
  真实联调 `python sdk/python/examples/quickstart.py`。
- 完整设计（包结构 / 异常层级 / 请求链路 / API 对照表 / 独立承载部署）：见
  `docs/独立承载服务与SDK集成设计.md`；SDK 使用说明见 `sdk/python/README.md`。

## 环境变量

`OPENWIKI_SERVER_DATA_DIR` / `_DB_PATH` / `_HTTP_HOST` / `_HTTP_PORT`（18011）/
`_GRPC_HOST` / `_GRPC_PORT`（50052）/ `_CELERY_BROKER` / `_CELERY_BACKEND` /
`_OPENWIKI_BIN` / `_OPENWIKI`（0 关闭内核）/ `_PROVIDER` / `_MODEL_ID`
（默认 `deepseek-v4-flash`，与本地 LLM 网关可用模型对齐，可用环境变量覆盖）/
`_UPDATE_TIMEOUT` / `_LOG_LEVEL`；Docker 额外使用 `HAPROXY_STATS_USER` /
`HAPROXY_STATS_PASSWORD`（HAProxy stats 登录）与 `OPENWIKI_HTTP_PORT` /
`OPENWIKI_GRPC_PORT` / `HAPROXY_STATS_PORT`（宿主端口映射）。
IKC Log Center 远程日志投递：`OPENWIKI_SERVER_LOG_CENTER_ENABLED` / `_URL` /
`_TOKEN` / `_TIMEOUT` / `_QUEUE_SIZE` / `_BATCH_SIZE`（HTTP POST `{url}/ingest`，
需安装 `openwiki-server[log-center]`）。LLM 凭据由容器环境直通，按
`OPENWIKI_SERVER_PROVIDER` 对应设置（如 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` /
`GEMINI_API_KEY` / `OPENROUTER_API_KEY`，见 `docs/deploy-offline.md` §5）。

## 测试

### 单元 / 冒烟（pytest）

```bash
PYTHONPATH=. python -m pytest tests -q
```

> 沙箱/CI 若禁止绑定 socket，gRPC 真链路测试自动 skip（进程内 handler 语义仍覆盖）。

### 命令行测试与调用（五类接口）

详细手册见 `docs/命令行测试与调用指南.md`：HTTP(curl) / CLI / gRPC / MCP / Celery(jobs) 全部命令，
已用仓库真实文档（`docs/进展.md`、`docs/解决方案.md`、`README.md`）实测通过。

一键全链路演练（探针 → CRUD → 真实文档 build → tree/page/search/stat/export →
merge/deprecate → 异步 job → CLI 等价命令，全部断言通过后打印 `ALL PASS`）：

```bash
bash scripts/wiki_api_drill.sh
```

常用命令速查（离线规则模式 `OPENWIKI_SERVER_OPENWIKI=0`，服务默认 `127.0.0.1:18011`）：

```bash
BASE=http://127.0.0.1:18011

# 起服务
export OPENWIKI_SERVER_DATA_DIR=/tmp/ow-live OPENWIKI_SERVER_OPENWIKI=0
openwiki-server serve http

# 创建 wiki（WID 取返回 data.wikiId）
curl -sS -X POST "$BASE/api/v1/wiki/wikis" -H 'Content-Type: application/json' \
  -d '{"kbId":"kb_live_demo","name":"演示","wikiConfig":{"granularity":"heading"}}'

# 用真实文档建页（docs/进展.md，heading 粒度切 11 页）
curl -sS -X POST "$BASE/api/v1/wiki/wikis/$WID/build" -H 'Content-Type: application/json' \
  -d "$(python -c "import json;print(json.dumps({'docId':'d1','title':'任务进展记录','tags':['运维'],'markdown':open('docs/进展.md',encoding='utf-8').read()}))")"

# 查询 / 检索 / 导出
curl -sS "$BASE/api/v1/wiki/wikis/$WID/tree?page=1&pageSize=20"
curl -sS --get "$BASE/api/v1/wiki/wikis/$WID/search" --data-urlencode "q=检索"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/stat"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/export?format=json"

# 异步任务：async=1 提交（JOB_ID 取返回 data.jobId）→ 手动执行 → 查询
curl -sS -X POST "$BASE/api/v1/wiki/wikis/$WID/build" -H 'Content-Type: application/json' \
  -d '{"async":"1","docId":"d_async","title":"异步示例","markdown":"# 异步示例"}'
curl -sS -X POST "$BASE/api/v1/wiki/jobs/$JOB_ID/run"
curl -sS "$BASE/api/v1/wiki/jobs/$JOB_ID"

# gRPC / MCP
python - <<'PY'
from openwiki_engine.interfaces.grpc_server import grpc_client
client = grpc_client("127.0.0.1", 50052)
print(client("Stat", {"wikiId": "wiki_<id>"}))
PY
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | openwiki-server serve mcp
```
