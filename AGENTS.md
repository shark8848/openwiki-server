# AGENTS.md

## Wiki 共享契约边界（2026-11-02，0.3.6 / SDK 0.2.0 / shared 0.42.0）

- 跨仓单一来源：`ikc-sdk-lib 0.42.0` 的 `ikc_sdk.core` 定义 Wiki 稳定 ID、`wikiConfig`、页面合并规则、
  `WikiEngine*` 引擎 DTO、core `WikiPageWriteItem`、六个 Celery 任务名/队列/载荷与 `WIKI_TM_API_BY_TASK`。
  `WikiBuildTaskPayload.model_id` 是任务级模型 ID，空值由引擎回落 `OPENWIKI_SERVER_MODEL_ID`。
  本仓禁止复制这些字段表或枚举。
- 本仓保留：`OpenWikiService` 用例编排、SQLite 持久化、OpenWiki CLI 子进程适配、OKF/规则切页、
  core HTTP 回写实现、Celery handler/worker 装配，以及 HTTP / gRPC / MCP / CLI 协议实现。
- 对外入口：**SDK + Celery 为主契约入口**，HTTP 是 SDK 传输面；gRPC / MCP / CLI 保留，不得删除或标废弃。
- 响应壳例外：openwiki-server 成功码为 `"0"`，与平台统一壳 `"000000"` 不同；未经评审不得混用。

## GitHub 令牌与看板同步契约（跨仓共享，2026-09-15）

- 仓库 `origin`：`git@github.com:shark8848/openwiki-server.git`（direct-push `main`，无 PR）。
- GitHub 用户级 **Projects v2** 同步令牌（Classic PAT，`project` scope）解析顺序：
  1. `/tmp/gh_token`（脚本约定位置，机器重启后 `/tmp` 会清空）；
  2. `~/.gh_token`（持久副本）。
  两者均为 `chmod 600`，**禁止入库**；缺令牌时应**报错退出**，不要静默带空 token 发请求。
  同一令牌可复用于其它项目的看板同步（本机各仓同款解析顺序）。
- **fine-grained PAT 无法访问用户级 Projects v2**（`FORBIDDEN: Resource not accessible by personal access token`），
  必须用 Classic PAT 或 GitHub App 安装令牌。
- 本仓**当前没有**看板同步脚本与 Projects 条目契约（`scripts/` 下无 `sync-github-projects.sh`）。
  若后续引入，参照 `/home/sharkyai/semantica-graph-server/scripts/sync-github-projects.sh`
  （按标题幂等 upsert，状态别名映射 Backlog / In progress / Done）并沿用上述令牌解析顺序。
