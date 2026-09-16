# 本地 Docker + litellm deepseek 测试进度（2026-09-01 晚）

## 目标
本地 docker 起 openwiki-server，通过 litellm 代理的 deepseek 模型（`deepseek-v4-flash`）验证
`OPENWIKI_SERVER_OPENWIKI=1` 建页链路，期望 build 返回 `mode: openwiki` 且页面入库；之后重建镜像、
导出 `docker/images/`、push && publish。

## 已完成
- 确认 litellm 链路可用：本地 `http://127.0.0.1:4000`（systemd 服务），主密钥
  `sk-litellm-master-key-2024`（与 /home/litellm/.env 一致），模型别名 `deepseek-v4-flash`；
  容器内经 `openai-compatible` 调 deepseek 生成 OKF 页面成功（手动复现验证过）。
- 修复 datetime 序列化 500：`openwiki_engine/adapters/openwiki.py` 新增 `_json_safe()`、
  `openwiki_engine/interfaces/http_app.py` 新增 `_JsonResponse(default=_json_default)`，
  全部 `_handle` 改用它；已加测试。
- **定位并修复核心 bug：wiki 根目录相对路径导致 openwiki 写入位置嵌套**
  - 根因：`Settings.data_dir` 默认 `"data"`（相对路径），`SqliteWikiStore.wiki_root()`
    返回 `data/wikis/<id>`；引擎把它原样传给 openwiki 子进程作 `HOME`/`cwd`，
    openwiki（Node `os.homedir()`）按相对路径解析，实际写入
    `wiki_root/data/wikis/<id>/.openwiki/wiki/`，引擎解析 `wiki_root/.openwiki/wiki/` 为空，
    build 静默降级为 `mode: rule`。
  - 修复（未提交）：
    - `openwiki_engine/config.py`：新增 `resolved_data_dir`（绝对路径），
      `resolved_db_path` / `wiki_root` 改用它；
    - `openwiki_engine/persistence/sqlite_store.py`：`wiki_root()` 返回绝对路径；
    - `openwiki_engine/adapters/openwiki.py`：`run_update`/`run_ingest` 入口
      `os.path.abspath(wiki_root)` 兜底；
    - `tests/test_engine.py`：新增 `test_wiki_root_is_absolute`。
- 测试：`python3 -m pytest tests/test_engine.py -q` → **20 passed, 1 skipped**。

## 当前未提交变更（git status）
- `openwiki_engine/adapters/openwiki.py`、`openwiki_engine/config.py`、
  `openwiki_engine/interfaces/http_app.py`、`openwiki_engine/persistence/sqlite_store.py`、
  `tests/test_engine.py`（83+/6-，含 datetime 修复与 wiki_root 绝对路径修复）
- 最近已提交：`3722bb6 fix: HAProxy timeout server 600s`、`16f2f33 feat: LLM 配置支持 litellm 代理`

## 待办（明天继续）
1. 重建镜像：`bash scripts/build_docker.sh`（会导出 `docker/images/openwiki-server_1.0.0.tar`）。
   - 注意：今晚重建被用户中断，镜像仍为旧版 `1443af46d976`，不含上述修复。
2. 重跑本地 docker 端到端：
   - `docker rm -f ow-local-llm && docker volume rm ow-local-test`（旧卷含嵌套残留，必须删）
   - 新容器：`docker run -d --name ow-local-llm --add-host host.docker.internal:host-gateway \
     -v ow-local-test:/app/data -e OPENWIKI_SERVER_OPENWIKI=1 \
     -e OPENWIKI_SERVER_PROVIDER=openai-compatible -e OPENWIKI_SERVER_MODEL_ID=deepseek-v4-flash \
     -e OPENWIKI_SERVER_UPDATE_TIMEOUT=600 \
     -e OPENAI_COMPATIBLE_API_KEY=sk-litellm-master-key-2024 \
     -e OPENAI_COMPATIBLE_BASE_URL=http://host.docker.internal:4000/v1 \
     -p 28011:8080 -p 28052:50052 -p 28405:8404 openwiki-server:1.0.0`
   - 建 wiki → `POST /api/v1/wiki/wikis`；build →
     `POST /api/v1/wiki/wikis/<id>/build`（deepseek 每次 2~3 分钟，curl 用 `--max-time 590`）
   - 验收：`mode: openwiki` 且 `total > 0`，且容器内
     `/app/data/wikis/<id>/.openwiki/wiki/` 有页面、不再出现
     `/app/data/wikis/<id>/data/wikis/<id>/` 嵌套。
3. 通过后：`git add -A && git commit`（版本 0.3.3，若需发版先升版本）→ push → publish
   （`scripts/publish-pypi.sh`），并同步远端 10.88.155.31 重新 load 新 tar 重部署。

## 环境备忘
- 测试容器 `ow-local-llm`（旧镜像）仍在跑：里面 `/usr/local/bin/openwiki` 被临时换成日志包装
  （日志写 `/tmp/engine-openwiki.log`），cli.js 已从镜像恢复；`/tmp/repro` 为复刻脚本。
  重建容器时直接 `rm -f` 即可，无需清理。
- 沙箱限制：docker 操作与访问 litellm 均需 `require_escalated`；本机沙箱内 curl 被拦。
- 之前踩坑：含中文/空格的 heredoc 内嵌 `EOF` 会炸，用 `<<'ENVFILE'` 分隔或 apply_patch。

## 已完成（2026-09-02）
- 重建镜像成功：`bash scripts/build_docker.sh --export` → `docker/images/openwiki-server_1.0.0.tar`（227M）；
  首次构建因 pypi.org 瞬时网络问题 grpcio 索引解析失败，重试即成功。
- 端到端验证通过（新容器 `ow-local-llm`，卷 `ow-local-test` 已重建）：
  - `POST /api/v1/wiki/wikis` 建 wiki `wiki-e2e-0902` 成功；
  - `POST /api/v1/wiki/wikis/wiki-e2e-0902/build` 返回 `mode: openwiki`、`total: 5`、`deprecated: 0`；
  - 容器内页面落盘 `/app/data/wikis/wiki-e2e-0902/.openwiki/wiki/`（topics/index、okf、openwiki-engine、
    commitments、quickstart、sources/doc-e2e-0902 等 8 个 md），无 `/data/wikis/<id>/data/wikis/` 嵌套；
  - `/api/v1/wiki/wikis/wiki-e2e-0902/stat`：pageCount=5、active=5、deprecated=0。
- 版本 pyproject.toml 已为 0.3.3；提交后 push + publish，并同步远端 10.88.155.31 重新 load 部署。

## 09-02 收尾
- PyPI 0.3.3（昨天 18:25 上传）不含晚间修复，已升 **0.3.4** 并发布成功
  （wheel+sdist，`https://pypi.org/project/openwiki-server/0.3.4/`）；SDK 0.1.0 未变。
- 用 0.3.4 重建镜像并导出：`docker/images/openwiki-server_1.0.0.tar`（227M，11:09）；
  镜像内 `openwiki_engine.__version__ == 0.3.4`。
- 部署包：`docker/images/openwiki-server-compose.tgz`（compose + engine.example.yaml + deploy-offline.md）。
- 提交记录：`fdc0476`（wiki_root/datetime 修复）、`4e96111`（升 0.3.4），均已 push origin main。
- **远端 10.88.155.31 同步受阻**：本机（192.168.90.x）SSH 22/443/2222 等端口全部超时（防火墙拦截），
  仅 HTTP 可达（18011 上仍跑 0.3.0 旧版）。MCP(8097) 是检索服务无部署能力。
  需在 10.88.x.x 局域网内的机器执行：
  ```
  scp docker/images/openwiki-server_1.0.0.tar root@10.88.155.31:/opt/openwiki-server/
  ssh root@10.88.155.31 'cd /opt/openwiki-server && docker load -i openwiki-server_1.0.0.tar && docker compose up -d --no-build --force-recreate'
  # 或非 compose：docker rm -f openwiki-server openwiki-server-worker 后按 deploy-offline.md §8.3/8.4 重新 run
  ```
  升级前远端当前版本 0.3.0；升级后 `curl http://10.88.155.31:18011/openapi.json` 应显示 0.3.4。

## 09-02 远端 LLM 模式测试（通过）
- 10.88.155.31 已升级 0.3.4（openapi.json 确认），health/ready OK。
- 建 wiki `wiki-remote-llm-0902` → build 返回 `mode: openwiki`、`total: 4`、`deprecated: 0`
  （deepseek-v4-flash 经 litellm，约 2.5 分钟）。
- stat pageCount=4/active=4、tree total=4、search(litellm)=4 hits。
- page 详情正常：OKF front matter datetime 字段以 ISO 字符串返回（`2026-09-02T09:34:55+00:00`），
  datetime 序列化修复在远端生效。

## 09-16 core 数据面回写（引擎 → core 内部写通道）

- 新增 `openwiki_engine/adapters/core_writeback.py`：构建完成后把**已决策页面**回写 core
  `POST /internal/wiki/build`（契约单一来源：ikc-core-service `docs/API接口与任务契约.md §2.5`，
  实现见 core `domain/services/wiki_write_service.py`）。
  - 只投递 core 契约字段（`_PAGE_FIELDS`，core 侧 `extra=forbid`）：`title/stableKey/level/parentPageId/
    parentStableKey/unitId/docId/tags/fields/links/sourceDocs/markdown/versionId`，本地字段
    （`pageId/wikiId/status/时间戳`）不外投；`parentPageId` 直接透传（与 SDK `wiki_ids` 派生同值），
    避免 core 二次派生。
  - 开关：未配置 `IKC_CORE_BASE_URL` 时整体关闭（返回 `None`，返回体形状与既有行为完全一致）；
    `IKC_CORE_WRITEBACK=0` 可显式关闭。鉴权头 `X-Internal-Token` = core `IKC_CORE_ADMIN_TOKEN`。
  - 回写失败**不阻断**本地构建（返回 `{"ok": false, "error": ...}` 并记 warning），保证引擎可独立运行。
  - `ENGINE_VERSION` 优先读 repo `pyproject.toml`（可编辑安装的 dist 元数据会滞后，实测 0.1.0 vs 0.3.4）。
- `application/service.py::build_from_doc`：启用时在返回体追加 `writeback` 字段（未启用不追加）。
- 分层口径：**抽什么在引擎**（切页/字段抽取/出链、OKF 上游），**怎么落地在 core**（稳定键 upsert、
  revision 递增与版本快照、doc 级增量废弃、build_log、审计）——落地语义只此一处实现，避免各引擎
  各写一套（G-05 `format=ttl` 类跨仓漂移的根因）。
- 验证：新增 `tests/test_core_writeback.py`（7 例：字段收窄、开关关闭、失败不阻断、版本漂移护栏、
  `http.server` 桩）；`pytest tests -q` → **32 passed, 1 skipped**。
- 跨仓实测（ikc-demo 知识库）：`build` 返回 `writeback={"ok": true, "created": 3, ...}`，core W-04 读面
  `pageCount=3 / active=3 / linkCount=5`。**坑**：回写用的 `docId` 必须是 core 已登记的文档——
  core 读面按来源文档可读性过滤，用未登记 docId 建的页会被判定不可见（表现为 `pageCount=0`）。
