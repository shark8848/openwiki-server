#!/usr/bin/env bash
set -euo pipefail

# 构建 openwiki-server Docker 镜像（Python 引擎 + Node openwiki 内核 + HAProxy 代理层，单镜像）。
#
# 用法：
#   bash scripts/build_docker.sh              # docker build
#   bash scripts/build_docker.sh --no-cache   # docker build --no-cache
#   bash scripts/build_docker.sh --export     # 构建并 docker save 导出到 docker/images/
#
# 环境变量：
#   IMAGE_TAG         镜像名:标签（默认 openwiki-server:<package.json version>）
#   OPENWIKI_VERSION  openwiki 内核版本（默认取 package.json dependencies.openwiki，脱掉 ^/~）

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

NO_CACHE=0
EXPORT=false
for arg in "$@"; do
  case "$arg" in
    --no-cache) NO_CACHE=1 ;;
    --export)   EXPORT=true ;;
    *)
      echo "[usage] 未知参数: $arg（支持 --no-cache）" >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "[docker] 未找到 docker 命令，请先安装 Docker" >&2
  exit 1
fi

# 从 package.json 解析服务版本与 openwiki 内核版本
VERSION="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' package.json | head -1)"
OPENWIKI_VERSION="$(sed -n 's/.*"openwiki": "\([^"]*\)".*/\1/p' package.json | head -1)"
OPENWIKI_VERSION="${OPENWIKI_VERSION#^}"
OPENWIKI_VERSION="${OPENWIKI_VERSION#~}"
if [[ -z "$VERSION" || -z "$OPENWIKI_VERSION" ]]; then
  echo "[docker] 无法从 package.json 解析版本（version=$VERSION, openwiki=$OPENWIKI_VERSION）" >&2
  exit 1
fi
IMAGE_TAG="${IMAGE_TAG:-openwiki-server:${VERSION}}"

build_args=(--build-arg "OPENWIKI_VERSION=${OPENWIKI_VERSION}")
if [[ "$NO_CACHE" == "1" ]]; then
  build_args+=(--no-cache)
fi

echo "[docker] 构建镜像 $IMAGE_TAG（引擎 + OpenWiki 内核@${OPENWIKI_VERSION} + HAProxy 代理层同镜像）..."
docker build "${build_args[@]}" -t "$IMAGE_TAG" .

if [ "$EXPORT" = true ]; then
  echo "[docker] 导出镜像到 docker/images/ ..."
  mkdir -p docker/images
  EXPORT_NAME="$(echo "${IMAGE_TAG%:*}" | tr '/:' '__')_${IMAGE_TAG##*:}.tar"
  docker save -o "docker/images/${EXPORT_NAME}" "$IMAGE_TAG"
  ls -lh "docker/images/${EXPORT_NAME}"
fi

echo "[docker] 构建完成: $IMAGE_TAG"
echo "[docker] 启动（HAProxy 入口 http://127.0.0.1:18011 / gRPC 50052 / stats 8404）：docker compose up -d"
