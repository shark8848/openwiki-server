#!/usr/bin/env bash
set -euo pipefail

# deploy-remote.sh — 目标服务器侧一键部署（离线或在线）
#
# 参考：ikc_extraction scripts/deploy_oneclick.sh（load -> 起服务 -> 健康检查）与
#      openwiki-server docs/deploy-offline.md（docker load + compose up --no-build）。
#
# 用法（在部署目录 /opt/openwiki-server 下执行）：
#   bash scripts/deploy-remote.sh                          # 自动 load _release/ 内镜像并 compose up
#   bash scripts/deploy-remote.sh --release-dir _release --image openwiki-server_1.0.0.tar
#   bash scripts/deploy-remote.sh --check                  # 仅检查现状（不 load / 不重启）
#   bash scripts/deploy-remote.sh --skip-load              # 镜像已 load，只重启服务
#
# 环境变量：
#   REMOTE_DIR        部署目录（默认当前目录）
#   OPENWIKI_HTTP_PORT 健康检查端口（默认读 .env，缺省 18011）

APP_DIR="${REMOTE_DIR:-$(pwd)}"
cd "$APP_DIR"

RELEASE_DIR="_release"
IMAGE_NAME=""
DO_CHECK=0
DO_LOAD=1

log() { echo -e "[deploy] $*"; }
warn(){ echo -e "[deploy][warn] $*" >&2; }
fail(){ echo -e "[deploy][ERROR] $*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release-dir)
      RELEASE_DIR="${2:-}"
      [[ -n "$RELEASE_DIR" ]] || fail "--release-dir 需要一个目录参数"
      shift 2
      ;;
    --image)
      IMAGE_NAME="${2:-}"
      [[ -n "$IMAGE_NAME" ]] || fail "--image 需要一个文件名参数"
      shift 2
      ;;
    --check)       DO_CHECK=1; shift ;;
    --skip-load)   DO_LOAD=0; shift ;;
    -h|--help)
      # 只打印文件头的注释块：shebang 之后可能先有 set/变量行，遇到第一行注释才开始，遇到第一行非注释收尾
      awk 'NR==1{next} /^#/{print substr($0,3); started=1} started && !/^#/{exit}' "$0"
      exit 0
      ;;
    *) fail "未知参数: $1（-h 查看帮助）" ;;
  esac
done

[[ -f docker-compose.yml ]] || fail "当前目录缺少 docker-compose.yml（应在部署目录 ${APP_DIR} 执行）"
have docker || fail "未找到 docker"
have curl || warn "未找到 curl，跳过健康检查"

# ---- 1) 找到待导入镜像 ----
if [[ -z "$IMAGE_NAME" ]]; then
  # 注意：set -e + pipefail 下 ls 无匹配会让赋值语句直接退出（静默且无提示），故补 || true
  IMAGE_NAME="$(ls "${RELEASE_DIR}"/openwiki-server_*.tar 2>/dev/null | head -1 | xargs -r basename || true)"
fi
if [[ -z "$IMAGE_NAME" || ! -f "${RELEASE_DIR}/${IMAGE_NAME}" ]]; then
  fail "未在 ${RELEASE_DIR}/ 找到镜像 tar（可用 --image 指定）"
fi

# ---- 2) 校验清单（可选） ----
SUMS="$(ls "${RELEASE_DIR}"/openwiki-server-*-SHA256SUMS.txt 2>/dev/null | head -1 || true)"
if [[ -n "$SUMS" ]]; then
  log "校验文件哈希: $SUMS"
  (cd "$RELEASE_DIR" && sha256sum -c "$(basename "$SUMS")")
fi

if [[ "$DO_CHECK" == "1" ]]; then
  log "--check: 只检查现状"
  docker images | grep -E "openwiki-server" || true
  docker compose ps || true
  exit 0
fi

# ---- 3) 导入镜像 ----
if [[ "$DO_LOAD" == "1" ]]; then
  log "导入镜像 ${RELEASE_DIR}/${IMAGE_NAME} ..."
  docker load -i "${RELEASE_DIR}/${IMAGE_NAME}"
fi

# ---- 4) .env 首次生成（缺失才生成；.env 含密钥，不入库） ----
if [[ ! -f .env && -f config/env.remote.example ]]; then
  cp config/env.remote.example .env
  warn "已从 config/env.remote.example 生成 .env（默认 OPENWIKI_SERVER_OPENWIKI=0 离线规则模式）。"
  warn "如需 LLM 合成：编辑 .env 设 OPENWIKI_SERVER_OPENWIKI=1 并填写对应 provider 的 key/base。"
fi

# ---- 5) 启动服务（不重新构建镜像） ----
log "docker compose up -d --no-build --force-recreate ..."
docker compose up -d --no-build --force-recreate

# ---- 6) 健康检查（最多 90s） ----
HTTP_PORT="$(grep -E '^OPENWIKI_HTTP_PORT=' .env 2>/dev/null | cut -d= -f2- | tr -d ' ' || true)"
HTTP_PORT="${HTTP_PORT:-18011}"
if have curl; then
  ok=0
  for _ in $(seq 1 90); do
    if curl -fsS -m 3 "http://127.0.0.1:${HTTP_PORT}/health" 2>/dev/null | grep -q '"status":"ok"'; then
      ok=1
      break
    fi
    sleep 1
  done
  [[ "$ok" == "1" ]] || fail "/health 未在 90s 内就绪"
  log "/health OK"
  curl -fsS -m 5 "http://127.0.0.1:${HTTP_PORT}/ready" >/dev/null && log "/ready OK"
  log "引擎版本: $(curl -fsS -m 5 "http://127.0.0.1:${HTTP_PORT}/openapi.json" 2>/dev/null | grep -o '"version":"[^"]*"' | head -1 || echo 未知)"
else
  warn "无 curl，跳过健康检查（请手动确认容器已启动）"
fi

log "部署完成。服务入口:"
log "  HTTP  http://127.0.0.1:${HTTP_PORT}/health"
log "  gRPC  ${HAPROXY_GRPC_PORT:-50052}（HAProxy 入口）"
docker compose ps
