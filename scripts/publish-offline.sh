#!/usr/bin/env bash
set -euo pipefail

# publish-offline.sh — openwiki-server 一键离线发布
#
# 参考其它项目约定：
#   - PyUploadX scripts/build-images.sh + docs/deploy-offline.md（构建导出 -> 打包 -> 传输 -> load/up）
#   - open-ikc scripts/build_docker.sh（docker save 产物命名 <repo>_<tag>.tar）
#   - ikc_extraction scripts/deploy_oneclick.sh（远端一键 load + 起服务 + 健康检查）
#
# 用法：
#   bash scripts/publish-offline.sh                 # 仅打包离线包（要求 docker/images/ 已有镜像 tar）
#   bash scripts/publish-offline.sh --build         # 构建镜像 + 导出 tar + 打包（推荐）
#   bash scripts/publish-offline.sh --build --push  # 并推送到远端，ssh 一键 load + compose up
#
# 参数：
#   --build      执行 docker build + docker save（= scripts/build_docker.sh --export）
#   --push       推送到远端（rsync/scp）+ 远程执行 scripts/deploy-remote.sh
#   --no-bundle  跳过离线包打包（配合 --build --push 使用）
#   -h|--help    显示本帮助
#
# 环境变量（可先写在 config/remote.env 固化，脚本自动读取）：
#   REMOTE_HOST   目标服务器（如 10.88.155.31）
#   REMOTE_USER   目标 SSH 用户（默认 root）
#   REMOTE_DIR    目标部署目录（默认 /opt/openwiki-server）
#   SSH_PORT      SSH 端口（默认 22）
#   IMAGE_TAG     镜像名:标签（默认 openwiki-server:<package.json version>）
#   TRANSFER      传输方式 rsync|scp（默认 rsync，缺失时自动用 scp）

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 可选的本地发布配置（不入库）：REMOTE_HOST / REMOTE_USER / REMOTE_DIR / SSH_PORT
if [[ -f config/remote.env ]]; then
  # shellcheck source=/dev/null
  source config/remote.env
fi

VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' package.json | head -1)"
IMAGE_TAG="${IMAGE_TAG:-openwiki-server:${VERSION}}"
IMAGES_DIR="docker/images"
TAR_NAME="$(printf '%s' "${IMAGE_TAG%:*}" | tr '/:' '__')_${IMAGE_TAG##*:}.tar"
TAR_PATH="${IMAGES_DIR}/${TAR_NAME}"
BUNDLE_NAME="openwiki-server-compose-${VERSION}.tgz"
BUNDLE_PATH="${IMAGES_DIR}/${BUNDLE_NAME}"
SUMS_PATH="${IMAGES_DIR}/openwiki-server-${VERSION}-SHA256SUMS.txt"

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/openwiki-server}"
SSH_PORT="${SSH_PORT:-22}"
TRANSFER="${TRANSFER:-}"

DO_BUILD=0
DO_PUSH=0
DO_BUNDLE=1

log() { echo -e "[publish] $*"; }
warn(){ echo -e "[publish][warn] $*" >&2; }
fail(){ echo -e "[publish][ERROR] $*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1; }

usage() {
  # 只打印文件头的注释块：shebang 之后可能先有 set/变量行，遇到第一行注释才开始，遇到第一行非注释收尾
  awk 'NR==1{next} /^#/{print substr($0,3); started=1} started && !/^#/{exit}' "$0"
}

for arg in "$@"; do
  case "$arg" in
    --build)     DO_BUILD=1 ;;
    --push)      DO_PUSH=1 ;;
    --no-bundle) DO_BUNDLE=0 ;;
    -h|--help)   usage; exit 0 ;;
    *) fail "未知参数: $arg（-h 查看帮助）" ;;
  esac
done

have docker || fail "未找到 docker，请先安装 Docker"

# ---- 1) 构建 + 导出 ----
if [[ "$DO_BUILD" == "1" ]]; then
  log "构建镜像 $IMAGE_TAG 并导出 $TAR_PATH ..."
  IMAGE_TAG="$IMAGE_TAG" bash scripts/build_docker.sh --export
fi
[[ -f "$TAR_PATH" ]] || fail "缺少镜像导出 $TAR_PATH；请先 --build（或手动 bash scripts/build_docker.sh --export）"

# compose 内 image 与本次镜像标签必须一致，否则远端 --no-build 启动会拉错/找不到镜像
COMPOSE_IMAGE="$(sed -n 's/^    image: \([^[:space:]]*\)/\1/p' docker-compose.yml | head -1)"
if [[ -n "$COMPOSE_IMAGE" && "$COMPOSE_IMAGE" != "$IMAGE_TAG" ]]; then
  fail "docker-compose.yml 中 image=${COMPOSE_IMAGE} 与 IMAGE_TAG=${IMAGE_TAG} 不一致，请先对齐"
fi

if [[ "$DO_BUNDLE" == "1" ]]; then
  # ---- 2) 打包部署配置（compose / env 模板 / 部署手册 / 远端部署脚本） ----
  mkdir -p "$IMAGES_DIR"
  log "打包离线包 $BUNDLE_PATH ..."
  tar czf "$BUNDLE_PATH" \
    docker-compose.yml \
    config/engine.example.yaml \
    config/env.remote.example \
    docs/deploy-offline.md \
    scripts/deploy-remote.sh
  # ---- 3) 校验清单 ----
  {
    (cd "$IMAGES_DIR" && sha256sum "$TAR_NAME" "$BUNDLE_NAME")
  } > "$SUMS_PATH"
  log "离线发布产物（docker/images/）:"
  ls -lh "$TAR_PATH" "$BUNDLE_PATH" "$SUMS_PATH"
  log "校验: cd docker/images && sha256sum -c $(basename "$SUMS_PATH")"
fi

if [[ "$DO_PUSH" == "1" ]]; then
  [[ -n "$REMOTE_HOST" ]] || fail "--push 需要 REMOTE_HOST（可在 config/remote.env 或环境变量设置）"
  have rsync || TRANSFER="${TRANSFER:-scp}"
  TRANSFER="${TRANSFER:-rsync}"

  log "推送到 ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/_release/"
  ssh -p "$SSH_PORT" -o BatchMode=yes "${REMOTE_USER}@${REMOTE_HOST}" \
    "mkdir -p '${REMOTE_DIR}/_release'" \
    || fail "SSH 连接 ${REMOTE_HOST} 失败（请确认免密登录或 SSH_PORT）"

  if [[ "$TRANSFER" == "rsync" ]]; then
    rsync -az --progress -e "ssh -p ${SSH_PORT}" \
      "$TAR_PATH" "$BUNDLE_PATH" "$SUMS_PATH" \
      "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/_release/"
  else
    scp -P "$SSH_PORT" \
      "$TAR_PATH" "$BUNDLE_PATH" "$SUMS_PATH" \
      "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/_release/"
  fi

  log "远端执行 deploy-remote.sh（load 镜像 + compose up + 健康检查）..."
  ssh -p "$SSH_PORT" -o BatchMode=yes "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd '${REMOTE_DIR}' && tar xzf '_release/${BUNDLE_NAME}' && bash scripts/deploy-remote.sh --release-dir '_release' --image '${TAR_NAME}'"
  log "远端部署完成: http://${REMOTE_HOST}:\${OPENWIKI_HTTP_PORT:-18011}/health"
fi

log "完成。离线人工传输方式见 docs/deploy-offline.md（scp/rsync/U 盘）。"
