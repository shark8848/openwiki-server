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
