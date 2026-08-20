#!/usr/bin/env bash
set -euo pipefail

# Docker 单镜像栈冒烟验证（参考 open-ikc scripts/docker_smoke.sh）：
#   1) 构建镜像（若 IMAGE_TAG 已存在则跳过构建，可用 --force-build 强制）
#   2) 起容器（HAProxy 对外 18011 HTTP / 50052 gRPC / 8404 stats）
#   3) 断言：/health、wiki create、build 建页、gRPC 经 HAProxy 真实调用、
#      stats 默认凭据 200 / 错误凭据 401、
#      引擎 18011 仅回环（容器 IP 连接被拒）、容器非 root 运行
# 用法：bash scripts/docker_smoke.sh [--force-build]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FORCE_BUILD=0
[[ "${1:-}" == "--force-build" ]] && FORCE_BUILD=1

VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' package.json | head -1)"
IMAGE_TAG="${IMAGE_TAG:-openwiki-server:${VERSION}}"
HTTP_PORT="${OPENWIKI_HTTP_PORT:-18011}"
GRPC_PORT="${OPENWIKI_GRPC_PORT:-50052}"
STATS_PORT="${HAPROXY_STATS_PORT:-8404}"
# 冒烟走离线规则模式（确定性、无需 LLM/网络）；内核可用性由镜像内 node + openwiki 安装覆盖
export OPENWIKI_SERVER_OPENWIKI=0

if ! command -v docker >/dev/null 2>&1; then
  echo "[smoke] 未找到 docker 命令" >&2
  exit 1
fi

if [[ "$FORCE_BUILD" == "1" ]] || ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  echo "[smoke] 构建镜像 $IMAGE_TAG ..."
  bash scripts/build_docker.sh
fi

cleanup() {
  docker compose down >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[smoke] 启动容器 ..."
docker compose up -d --no-build >/dev/null

# 等待 HAProxy 入口就绪（最多 60s）
for _ in $(seq 1 60); do
  if curl -fsS -m 3 "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

fail() {
  echo "[smoke] FAIL: $1" >&2
  exit 1
}

echo "[smoke] 1. /health 经 HAProxy"
curl -fsS -m 5 "http://127.0.0.1:${HTTP_PORT}/health" | grep -q '"status":"ok"' || fail "/health 未就绪"

echo "[smoke] 2. 创建 wiki（envelope errCode=0）"
CREATE=$(curl -s -m 15 -X POST "http://127.0.0.1:${HTTP_PORT}/api/v1/wiki/wikis" \
  -H "Content-Type: application/json" \
  -d '{"kbId":"kb_docker_smoke","name":"Docker 冒烟 Wiki"}')
echo "$CREATE" | grep -q '"errCode":"0"' || fail "create 失败: $CREATE"
WID=$(echo "$CREATE" | sed -n 's/.*"wikiId":"\([^"]*\)".*/\1/p')
[[ -n "$WID" ]] || fail "create 未返回 wikiId: $CREATE"

echo "[smoke] 3. build 建页（规则切页 total=1）"
BUILD=$(curl -s -m 15 -X POST "http://127.0.0.1:${HTTP_PORT}/api/v1/wiki/wikis/${WID}/build" \
  -H "Content-Type: application/json" \
  -d '{"docId":"doc1","title":"产品手册","markdown":"# 产品手册\n\n## 安装\n\n安装说明。负责人：张三"}')
echo "$BUILD" | grep -q '"total":1' || fail "build 失败: $BUILD"

echo "[smoke] 4. gRPC 经 HAProxy（真实调用 Stat 应 200404）"
GRPC_RESULT=$(python - <<'PY' 2>&1 || true
import json
from openwiki_engine.interfaces.grpc_server import grpc_client
r = grpc_client("127.0.0.1", int(__import__("os").environ.get("OPENWIKI_GRPC_PORT", "50052")))("Stat", {"wikiId": "nope"})
print(r.get("errCode"))
PY
)
[[ "$GRPC_RESULT" == "200404" ]] || fail "gRPC 经 HAProxy 调用异常: $GRPC_RESULT"

echo "[smoke] 5. stats 默认凭据 200 / 错误凭据 401"
C1=$(curl -s -m 5 -o /dev/null -w '%{http_code}' -u "admin:change-me" "http://127.0.0.1:${STATS_PORT}/")
[[ "$C1" == "200" ]] || fail "stats 默认凭据应 200，实际 $C1"
C2=$(curl -s -m 5 -o /dev/null -w '%{http_code}' -u "admin:wrong" "http://127.0.0.1:${STATS_PORT}/")
[[ "$C2" == "401" ]] || fail "stats 错误凭据应 401，实际 $C2"

echo "[smoke] 6. 引擎 18011 仅回环（容器 IP 连接应被拒）"
CID=$(docker compose ps -q app)
docker exec "$CID" python -c "
import socket, subprocess, sys
ip = subprocess.check_output(['hostname', '-i']).decode().strip()
s = socket.socket()
try:
    s.settimeout(1); s.connect((ip, 18011))
except (ConnectionRefusedError, OSError):
    sys.exit(0)
finally:
    s.close()
sys.exit(1)
" || fail "容器 IP 可连 18011，回环隔离失效"

echo "[smoke] 7. 容器非 root 运行"
docker exec "$CID" sh -c 'test "$(id -u)" = "1000"' || fail "容器应以 uid 1000 运行"

echo "[smoke] PASS：单镜像栈全部冒烟通过（入口 ${HTTP_PORT} / gRPC ${GRPC_PORT} / stats ${STATS_PORT}）"
