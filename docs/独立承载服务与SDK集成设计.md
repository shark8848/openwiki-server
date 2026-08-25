# OpenWiki Server 独立承载服务与 SDK 集成设计（openwiki-server-sdk）

> 版本：1.0.0
> 状态：已发布
> 适用范围：面向外部应用的集成客户端 SDK；openwiki-server 作为**独立承载服务**（独立进程/容器，
> 对外暴露 HTTP 18011 / gRPC 50052）运行，应用侧通过本 SDK 快速集成 wiki 能力。
> 参考 open-ikc 的 SDK 定义（`/home/open-ikc/sdk/python`，`open-ikc-sdk`）：
> 同协议解耦、同 envelope、同 traceId/认证头约定、同异常层级与重试语义。

## 1. 背景与目标

openwiki-server 以五类接口（HTTP / gRPC / Celery / MCP / CLI）对外提供 wiki 引擎能力：
wiki 实例 CRUD、按文档建页（build/merge/deprecate/update/ingest）、页面树/检索/统计/导出、
异步任务（jobs）。应用侧直接调 HTTP 需要自行处理统一响应壳、traceId、错误码映射、重试与超时，
成本高且易错。本 SDK 的目标：

1. 封装全部 wiki 能力为类型安全、可读的 Python 调用，屏蔽 HTTP 细节。
2. 内置 23 位数字 traceId 生成/复用、Bearer 认证、身份头透传（X-User-Id / X-Tenant-Id / X-User-Roles）。
3. 统一错误码 → 异常层级映射，业务失败与传输失败可区分捕获。
4. 与服务端实现完全解耦：SDK 只依赖对外 HTTP 协议（`/api/v1/wiki/*` + `/openapi.json`），
   不依赖 `openwiki_engine/` 任何内部代码。
5. 提供同步（`OpenWikiServerClient`）与异步（`AsyncOpenWikiServerClient`）双客户端，共享同一套模型。

## 2. 边界与冲突隔离

| 维度 | 约定 |
| --- | --- |
| 写范围 | 仅 `sdk/python/`、本文档与 README；**不修改** `openwiki_engine/`、`tests/` |
| 依赖 | 仅第三方 `httpx`；不引入 fastapi / pydantic / typer，不读服务端内部模块 |
| 命名 | 包名 `openwiki-server-sdk`，导入名 `openwiki_server_sdk`，与服务端包 `openwiki_engine` 区分 |
| 耦合面 | 仅 HTTP 协议：路径 `/api/v1/wiki/*`、统一响应壳（`{traceId,errCode,errMsg,data}`）、
  错误码（`0 / 200001 / 200404 / 200409 / 200500`）、Header 约定（`X-Trace-Id`） |
| 运行时契约 | 可选诊断方法 `fetch_openapi()`，以 FastAPI 自动生成的 `/openapi.json` 为运行时接口目录自检 |
| 部署拓扑 | SDK 面向「独立承载服务」：`openwiki-server serve http`（本地）或 Docker 单镜像栈
  （HAProxy 入口 `18011`），与消费方进程完全解耦 |

## 3. 包结构与命名

```
sdk/python/
  pyproject.toml          # 独立打包：openwiki-server-sdk，核心依赖 httpx；可选 dev(pytest)
  README.md               # SDK 使用说明（安装 / 快速开始 / 环境变量 / 联调冒烟）
  openwiki_server_sdk/
    __init__.py           # 导出 OpenWikiServerClient / AsyncOpenWikiServerClient / 异常 / 模型
    _version.py           # SDK 版本号（1.0.0）
    _bootstrap.py         # client_from_env / async_client_from_env：环境变量 -> 客户端
    client.py             # 主客户端 + wiki/jobs 域子客户端 + raw 逃生口 + fetch_openapi
    async_client.py       # 异步客户端（httpx.AsyncClient），领域方法同同步客户端
    transport.py          # 同步 HTTP 传输：超时、重试、统一壳解析
    transport_async.py    # 异步 HTTP 传输：与同步共享超时/重试/解析语义
    envelope.py           # 统一响应壳解析（errCode/errMsg/data/traceId，成功码 "0"）
    errors.py             # 异常层级 + 错误码映射表（200001/200404/200409/200500）
    trace.py              # 23 位数字 traceId 生成/复用
    headers.py            # 认证头 + 身份头构建（CallerIdentity）
    models/
      wiki.py             # wiki 数据模型（WikiMeta/WikiTreeData/WikiPageData/WikiSearchData/
                          #   WikiStat/WikiExport/BuildResult/WikiJob/...）
  examples/
    quickstart.py         # 同步全链路冒烟：创建 -> 真实文档建页 -> 查询/检索/导出 -> 异步 job -> 清理
    async_quickstart.py   # 异步客户端示例
  tests/                  # SDK 自测（httpx.MockTransport，无需起服务）
```

命名约定（与 open-ikc SDK 一致）：

- SDK 方法按领域子客户端组织：`client.wikis.create/list/get/delete/tree/page/search/stat/export/
  build/merge/deprecate_doc/update/ingest`、`client.jobs.run/get/list`；方法名蛇形，
  请求参数与响应字段**沿用服务端 API 的 camelCase**（`kbId`、`wikiId`、`docId`、`pageId`…），与接口 1:1 对应。
- 数据模型用 `dataclass` + `from_dict()` 构造；未知字段收进 `extra: dict` 透传，不阻断解析。
- 每个模型带 `to_dict()`，方便日志与二次加工。

## 4. 核心对象模型

### 4.1 客户端配置

```python
client = OpenWikiServerClient(
    base_url="http://127.0.0.1:18011",     # 独立承载服务地址（必填）
    token="YOUR_TOKEN",                     # Bearer Token；缺省读环境变量 OPENWIKI_SERVER_TOKEN
    timeout=(5, 60),                        # (连接超时, 读写超时) 秒
    max_retries=2,                          # 传输级重试（502/503/504，GET 幂等）
    identity=CallerIdentity(user_id="u1", tenant_id="t1", roles=["km_admin"]),
    extra_headers={"X-Custom": "v"},        # 自定义头
    trace_id=None,                          # 固定 traceId（联调用）；缺省按请求生成
)
```

- `client_from_env()`：读 `OPENWIKI_SERVER_BASE_URL`（默认 `http://127.0.0.1:18011`）/
  `OPENWIKI_SERVER_TOKEN` / `OPENWIKI_SERVER_USER_ID` / `OPENWIKI_SERVER_TENANT_ID` /
  `OPENWIKI_SERVER_ROLES`；`async_client_from_env()` 语义一致。
- 客户端实现 `AutoCloseable`（`close()` / 上下文管理器）。

### 4.2 响应壳与数据模型

`Envelope` 为统一壳：`err_code / err_msg / data / trace_id / ok`（`err_code == "0"`）。
领域方法返回强类型模型（`WikiMeta` / `WikiTreeData` / `WikiPageData` / `WikiSearchData` /
`WikiStat` / `WikiExport` / `BuildResult` / `WikiJob`）；`raw()` 逃生口返回原始 `Envelope`。

### 4.3 异常层级

```
OpenWikiServerError
├── OpenWikiServerTransportError        # 传输层异常（含 traceId）
│   ├── OpenWikiServerConnectionError   # 连接失败
│   ├── OpenWikiServerTimeoutError      # 读超时
│   ├── OpenWikiServerProtocolError     # 响应不符统一壳协议
│   └── OpenWikiServerHTTPStatusError   # HTTP 非 2xx 且非统一壳（含 statusCode/body）
└── OpenWikiServerAPIError              # 业务异常（errCode/errMsg/traceId）
    ├── OpenWikiServerValidationError   # 200001 参数非法
    ├── OpenWikiServerNotFoundError     # 200404 资源不存在
    ├── OpenWikiServerConflictError     # 200409 冲突
    ├── OpenWikiServerSystemError       # 200500 系统错误
    └── OpenWikiServerBusinessError     # 其他业务错误码兜底
```

错误码映射：`200001→Validation`、`200404→NotFound`、`200409→Conflict`、`200500→System`，其余→`Business`。

## 5. 请求链路约定

1. 每次请求生成/复用 23 位数字 traceId（`X-Trace-Id` 与 `X-Request-Id` 头）。
2. 有 token 时携带 `Authorization: Bearer <token>`。
3. 身份头透传：`X-User-Id` / `X-Tenant-Id` / `X-User-Roles`（逗号分隔）。
4. 统一壳 `errCode != "0"` 时抛对应 `OpenWikiServerAPIError`；`raw()` 返回原始壳。
5. HTTP 状态 502/503/504 自动重试（默认 2 次，指数退避）；POST 仅显式携带 `reqId` 时允许重试。

## 6. 能力 API 对照（HTTP 协议面）

| 域 | 方法 | 服务端端点 |
| --- | --- | --- |
| wikis | `create(kbId, name, wikiId, tenantId, ownerId, wikiConfig)` | `POST /api/v1/wiki/wikis` |
| wikis | `list(tenantId, ownerId)` | `GET /api/v1/wiki/wikis` |
| wikis | `get(wikiId)` / `delete(wikiId)` | `GET|DELETE /api/v1/wiki/wikis/{wiki_id}` |
| wikis | `tree(wikiId, page, pageSize)` | `GET .../wikis/{wiki_id}/tree` |
| wikis | `page(wikiId, pageId)` | `GET .../wikis/{wiki_id}/page?pageId=` |
| wikis | `search(wikiId, q, tag, limit)` | `GET .../wikis/{wiki_id}/search` |
| wikis | `stat(wikiId)` | `GET .../wikis/{wiki_id}/stat` |
| wikis | `export(wikiId, format)` | `GET .../wikis/{wiki_id}/export` |
| wikis | `build(wikiId, docId, title, tags, markdown, wikiConfig, async_)` | `POST .../wikis/{wiki_id}/build` |
| wikis | `merge(wikiId, pages, docId)` | `POST .../wikis/{wiki_id}/merge` |
| wikis | `deprecate_doc(wikiId, docId)` | `POST .../wikis/{wiki_id}/deprecate-doc` |
| wikis | `update(wikiId, message)` / `ingest(wikiId, connector)` | `POST .../wikis/{wiki_id}/update|ingest` |
| jobs | `run(jobId)` / `get(jobId)` / `list(wikiId, limit)` | `POST /api/v1/wiki/jobs/{job_id}/run`、`GET .../jobs/{job_id}`、`GET .../jobs` |
| 低层 | `request(method, path, ...)` / `raw(...)` / `fetch_openapi()` | 任意 `/api/v1/wiki/*`、`/openapi.json` |

> `build(async_=True)` 返回 `WikiJob`（任务登记结果）；broker 不可达时任务保持 `pending`，
> 应用侧可调 `jobs.run(jobId)` 手动同步执行，或由服务端 Celery worker 消费。

## 7. 独立承载服务部署（SDK 消费方视角）

```bash
# 本地进程承载（离线规则模式，确定性、免 LLM/网络）
export OPENWIKI_SERVER_DATA_DIR=/tmp/ow-live OPENWIKI_SERVER_OPENWIKI=0
openwiki-server serve http          # 默认 18011

# Docker 单镜像栈承载（HAProxy 对外入口，HTTP 18011 / gRPC 50052 / stats 8404）
bash scripts/build_docker.sh && docker compose up -d
bash scripts/docker_smoke.sh        # 7 项断言冒烟
```

应用侧只需配置 `OPENWIKI_SERVER_BASE_URL` 指向承载服务地址即可集成，与承载方式（本地/Docker/远端）无关。

## 8. 联调冒烟

```bash
# 先启动独立承载服务（见 §7）
python sdk/python/examples/quickstart.py        # 同步全链路（真实文档 docs/进展.md）
python sdk/python/examples/async_quickstart.py  # 异步客户端
```

## 9. 自测

```bash
cd sdk/python && PYTHONPATH=. python -m pytest tests -q
```

> 测试基于 `httpx.MockTransport`，无需起真实服务；36 例覆盖
> envelope/错误映射/traceId/模型解析/领域方法/请求头/环境变量引导/异步客户端。
