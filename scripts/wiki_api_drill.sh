#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/sharkyai/openwiki-server
PORT=18021
BASE="http://127.0.0.1:${PORT}"
DATA=/tmp/ow-live

rm -rf "$DATA" && mkdir -p "$DATA"
export OPENWIKI_SERVER_DATA_DIR=$DATA
export OPENWIKI_SERVER_OPENWIKI=0
export OPENWIKI_SERVER_HTTP_PORT=$PORT

cd "$ROOT"
uvicorn openwiki_engine.interfaces.http_app:create_app --factory --host 127.0.0.1 --port "$PORT" \
  > "$DATA/uvicorn.log" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  curl -fsS -m 2 "$BASE/health" >/dev/null 2>&1 && break
  sleep 0.5
done

say(){ echo; echo "### $*"; }
j() { python -c "import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }

say "0. 存活/就绪探针"
curl -sS "$BASE/health"; echo
curl -sS "$BASE/ready"; echo

say "1. 创建 wiki（kbId=kb_live_demo，granularity=heading + extractFields）"
CREATE=$(curl -sS -X POST "$BASE/api/v1/wiki/wikis" -H 'Content-Type: application/json' \
  -d '{"kbId":"kb_live_demo","name":"OpenWiki 服务能力演示","tenantId":"t1","ownerId":"o1","wikiConfig":{"granularity":"heading","extractFields":["负责人","状态"]}}')
echo "$CREATE"
WID=$(echo "$CREATE" | j "d['data']['wikiId']")
echo "wikiId=$WID"

say "2. 列表 / 详情"
curl -sS "$BASE/api/v1/wiki/wikis?tenantId=t1"; echo
curl -sS "$BASE/api/v1/wiki/wikis/$WID"; echo

say "3. build：真实文档 docs/进展.md（粒度 heading，规则切页）"
B1=$(curl -sS -X POST "$BASE/api/v1/wiki/wikis/$WID/build" -H 'Content-Type: application/json' \
  -d "$(python -c "import json;print(json.dumps({'docId':'doc_progress','title':'任务进展记录','tags':['运维','进展'],'markdown':open('docs/进展.md',encoding='utf-8').read()}))")")
echo "$B1" | j "json.dumps({'mode':d['data']['mode'],'total':d['data']['total'],'deprecated':d['data']['deprecated']}, ensure_ascii=False)"
echo "$B1" | j "[p['title'] for p in d['data']['pages']]"

say "4. build：真实文档 docs/解决方案.md（标题+tags 不同）"
B2=$(curl -sS -X POST "$BASE/api/v1/wiki/wikis/$WID/build" -H 'Content-Type: application/json' \
  -d "$(python -c "import json;print(json.dumps({'docId':'doc_design','title':'OpenWiki Server 解决方案','tags':['方案','架构'],'markdown':open('docs/解决方案.md',encoding='utf-8').read()}))")")
echo "$B2" | j "json.dumps({'mode':d['data']['mode'],'total':d['data']['total']}, ensure_ascii=False)"

say "5. 页面树 tree（库级）"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/tree?page=1&pageSize=20"; echo

PID=$(echo "$B2" | j "d['data']['pages'][0]['pageId']")

say "6. 单页详情 page（pageId=$PID）"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/page?pageId=$PID"; echo

say "7. 检索 search（真实词：HAProxy / 检索 / tag 过滤）"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/search?q=HAProxy&limit=10"; echo
curl -sS --get "$BASE/api/v1/wiki/wikis/$WID/search" --data-urlencode "q=检索"; echo
curl -sS --get "$BASE/api/v1/wiki/wikis/$WID/search" --data-urlencode "tag=方案"; echo

say "8. 统计 stat"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/stat"; echo

say "9. 导出 export（jsonl / json）"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/export?format=jsonl" | j "json.dumps({'total':d['data']['total'],'first':d['data']['content'].splitlines()[0]}, ensure_ascii=False)"
curl -sS "$BASE/api/v1/wiki/wikis/$WID/export?format=json" | j "d['data']['total']"

say "10. merge：显式页面记录增量合并"
curl -sS -X POST "$BASE/api/v1/wiki/wikis/$WID/merge" -H 'Content-Type: application/json' \
  -d '{"docId":"doc_merge","pages":[{"title":"开放平台统一认证","tags":["认证","设计"],"fields":{"负责人":"安全组"},"markdown":"# 开放平台统一认证\n\nOAuth2/SSO 接入说明。"}]}'; echo

say "11. deprecate-doc：按 docId 增量废弃"
curl -sS -X POST "$BASE/api/v1/wiki/wikis/$WID/deprecate-doc" -H 'Content-Type: application/json' \
  -d '{"docId":"doc_merge"}'; echo

say "12. jobs：async=1 提交 → 列表 → 手动执行 → 查询结果"
JOB=$(curl -sS -X POST "$BASE/api/v1/wiki/wikis/$WID/build" -H 'Content-Type: application/json' \
  -d "$(python -c "import json;print(json.dumps({'async':'1','docId':'doc_async','title':'异步构建示例','markdown':open('README.md',encoding='utf-8').read()}))")")
echo "$JOB"
JID=$(echo "$JOB" | j "d['data']['jobId']")
curl -sS "$BASE/api/v1/wiki/jobs?wikiId=$WID"; echo
curl -sS -X POST "$BASE/api/v1/wiki/jobs/$JID/run"; echo
curl -sS "$BASE/api/v1/wiki/jobs/$JID" | j "json.dumps({'jobId':d['data']['jobId'],'task':d['data']['task'],'status':d['data']['status']}, ensure_ascii=False)"

say "13. 删除 wiki（级联清库与文件）"
curl -sS -X DELETE "$BASE/api/v1/wiki/wikis/$WID"; echo

say "14. CLI 等价命令（openwiki-server 入口，离线规则模式）"
cli() { PYTHONPATH="$ROOT" python -c "from openwiki_engine.interfaces.cli import app; app()" "$@"; }
cli create --kb-id kb_cli_demo --name "CLI 演示 Wiki" --config '{"granularity":"heading"}'
WID2=$(cli list | j "d['items'][0]['wikiId']")
echo "cli wikiId=$WID2"
cli build "$WID2" --doc-id cli_doc1 --title 命令行构建 --tags cli,示例 --markdown $'# 命令行构建\n\n## 用法\n\nopenwiki-server build <wikiId> --markdown "..."'
cli tree "$WID2" | j "d['total']"
cli search "$WID2" --q 用法 | j "d['total']"
cli stat "$WID2" | j "json.dumps(d, ensure_ascii=False)"
cli export "$WID2" --format json | j "d['total']"
cli delete "$WID2" >/dev/null

echo
echo "=== ALL PASS ==="
