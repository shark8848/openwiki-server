# openwiki-server-sdk

OpenWiki Server **独立承载服务**（wiki 引擎作为独立进程/容器对外提供）的应用集成 SDK。**v1.0.0**。

设计文档：`docs/独立承载服务与SDK集成设计.md`（仓库根目录）。

## 安装

```bash
pip install sdk/python
```

仅依赖 `httpx`；测试依赖 `pytest`（`pip install "sdk/python[dev]"`）。

## 快速开始（同步）

```python
from openwiki_server_sdk import OpenWikiServerClient

client = OpenWikiServerClient(
    base_url="http://127.0.0.1:18011",   # 独立承载服务地址（本地 serve / Docker 入口）
    token="<TOKEN>",                      # 可选；服务端启用鉴权时必填
)

# 1. 创建 wiki 实例（wikiId 由 kbId 稳定派生）
wiki = client.wikis.create(
    kbId="kb_demo",
    name="产品知识库",
    tenantId="t1",
    wikiConfig={"granularity": "heading", "extractFields": ["负责人"]},
)
print(wiki.wikiId, wiki.wikiConfig)

# 2. 按真实文档建页（heading 粒度按标题切页；离线自动规则降级）
result = client.wikis.build(
    wiki.wikiId,
    docId="doc_1",
    title="产品手册",
    tags=["手册"],
    markdown=open("docs/进展.md", encoding="utf-8").read(),
)
print(result.mode, result.total, [p.title for p in result.pages])

# 3. 查询 / 检索 / 统计 / 导出
tree = client.wikis.tree(wiki.wikiId, pageSize=50)
hits = client.wikis.search(wiki.wikiId, q="安装", tag="手册")
stat = client.wikis.stat(wiki.wikiId)
export = client.wikis.export(wiki.wikiId, format="jsonl")

# 4. 异步任务（async_=True 登记 job，可手动执行或由 Celery worker 消费）
job = client.wikis.build(wiki.wikiId, docId="doc_2", title="异步", markdown="# 异步", async_=True)
job = client.jobs.run(job.jobId)      # broker 不可达时手动执行
print(job.status)

client.close()
```

## 异步客户端

```python
import asyncio
from openwiki_server_sdk import AsyncOpenWikiServerClient

async def main():
    async with AsyncOpenWikiServerClient(base_url="http://127.0.0.1:18011") as client:
        wiki = await client.wikis.create(kbId="kb_demo2", name="异步演示")
        tree = await client.wikis.tree(wiki.wikiId)
        print(tree.total)

asyncio.run(main())
```

同步与异步客户端共享同一套模型与错误映射；`request`/`raw`/`fetch_openapi` 低层调用与重试语义一致。

## 环境变量引导

```bash
export OPENWIKI_SERVER_BASE_URL=http://127.0.0.1:18011
export OPENWIKI_SERVER_TOKEN=<token>          # 可选
export OPENWIKI_SERVER_USER_ID=u1             # 可选，身份头 X-User-Id
export OPENWIKI_SERVER_TENANT_ID=t1           # 可选，身份头 X-Tenant-Id
export OPENWIKI_SERVER_ROLES=km_admin,viewer  # 可选，身份头 X-User-Roles
```

```python
from openwiki_server_sdk import client_from_env, async_client_from_env

client = client_from_env()
# 等价：OpenWikiServerClient(base_url=os.environ["OPENWIKI_SERVER_BASE_URL"], ...)
```

## 领域方法总览

- `client.wikis`：`create / list / get / delete / tree / page / search / stat / export / build / merge / deprecate_doc / update / ingest`
- `client.jobs`：`run / get / list`
- 低层：`request(method, path, ...)` / `raw(...)`（不抛业务异常）/ `fetch_openapi()`（运行时接口目录自检）

## 异常层级

```
OpenWikiServerError
├── OpenWikiServerTransportError        # 传输层（含 traceId）
│   ├── OpenWikiServerConnectionError
│   ├── OpenWikiServerTimeoutError
│   ├── OpenWikiServerProtocolError     # 响应不符统一壳协议
│   └── OpenWikiServerHTTPStatusError   # 非 2xx 且非统一壳
└── OpenWikiServerAPIError              # 业务异常（errCode/errMsg/traceId）
    ├── OpenWikiServerValidationError   # 200001 参数非法
    ├── OpenWikiServerNotFoundError     # 200404 资源不存在
    ├── OpenWikiServerConflictError     # 200409 冲突
    ├── OpenWikiServerSystemError       # 200500 系统错误
    └── OpenWikiServerBusinessError     # 其他错误码兜底
```

## 联调冒烟

先启动独立承载服务（离线规则模式可免 LLM/网络）：

```bash
export OPENWIKI_SERVER_DATA_DIR=/tmp/ow-live OPENWIKI_SERVER_OPENWIKI=0
openwiki-server serve http        # 默认 18011（Docker：docker compose up -d 入口 18011）
```

```bash
# 同步全链路：创建实例 → 真实文档建页 → 树/检索/统计/导出 → 异步 job → 清理
python sdk/python/examples/quickstart.py

# 异步客户端示例
python sdk/python/examples/async_quickstart.py
```

## 自测

```bash
cd sdk/python && PYTHONPATH=. python -m pytest tests -q
```

> 测试基于 `httpx.MockTransport`，无需起真实服务。
