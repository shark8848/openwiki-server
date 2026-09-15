# AGENTS.md

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
