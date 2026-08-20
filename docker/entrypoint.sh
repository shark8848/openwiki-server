#!/bin/sh
set -eu

# 单镜像入口：
#   api 角色（默认）：启动引擎（uvicorn HTTP 127.0.0.1:18011 + gRPC 127.0.0.1:50052，
#                     仅监听回环不对外），再前台运行 HAProxy 作为唯一对外入口
#                     （:8080 HTTP / :50052 gRPC / :8404 stats）。
#   worker 角色：启动 Celery worker（需 Redis broker/backend，见 docker-compose.yml）。
# 用法：openwiki-entrypoint.sh [api|worker]，或设置 OPENWIKI_SERVER_ROLE 环境变量。

ROLE="${1:-${OPENWIKI_SERVER_ROLE:-api}}"

# 用 HAPROXY_STATS_USER / HAPROXY_STATS_PASSWORD 渲染 HAProxy 配置模板
# （写到 /tmp，appuser 可写）
envsubst '${HAPROXY_STATS_USER} ${HAPROXY_STATS_PASSWORD}' \
  < /etc/haproxy/haproxy.cfg.tmpl \
  > /tmp/haproxy.cfg

# 默认 stats 凭据告警（admin/change-me 仅限本地试用，生产必须设置 HAPROXY_STATS_PASSWORD）
if [ "${HAPROXY_STATS_USER:-admin}" = "admin" ] && [ "${HAPROXY_STATS_PASSWORD:-change-me}" = "change-me" ]; then
  echo "[warn] HAProxy stats 使用默认凭据 admin/change-me，生产请设置 HAPROXY_STATS_PASSWORD" >&2
fi

# 数据目录（默认挂载卷 /app/data）
DATA_DIR="${OPENWIKI_SERVER_DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"

if [ "$ROLE" = "worker" ]; then
  exec openwiki-server serve worker
fi
if [ "$ROLE" != "api" ]; then
  echo "[error] 未知角色: $ROLE（支持 api / worker）" >&2
  exit 1
fi

# 等待 host:port 就绪（最多 60 次 × 0.5s），进程退出则 fail-fast
wait_port() {
  host="$1"
  port="$2"
  pid="$3"
  tries="${4:-60}"
  for _ in $(seq 1 "$tries"); do
    if python -c "import socket; socket.create_connection(('$host', $port), timeout=1).close()" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[error] 进程 pid=$pid 启动后退出，容器终止以便重启" >&2
      return 1
    fi
    sleep 0.5
  done
  echo "[error] $host:$port 未在 $((tries / 2))s 内就绪，容器终止以便重启" >&2
  return 1
}

# 引擎只监听回环地址，避免绕过 HAProxy 直连
python -m uvicorn openwiki_engine.interfaces.http_app:create_app \
  --factory --host 127.0.0.1 --port 18011 &
APP_PID=$!

python -c "from openwiki_engine.interfaces.grpc_server import serve_grpc; serve_grpc(host='127.0.0.1', port=50052)" &
GRPC_PID=$!

wait_port 127.0.0.1 18011 "$APP_PID" || exit 1
wait_port 127.0.0.1 50052 "$GRPC_PID" || exit 1

# 前台运行 HAProxy（容器退出时同步清理引擎进程）
/usr/sbin/haproxy -f /tmp/haproxy.cfg &
HAPROXY_PID=$!

forward() {
  kill -"$1" "$APP_PID" "$GRPC_PID" "$HAPROXY_PID" 2>/dev/null || true
}
trap 'forward TERM' TERM
trap 'forward INT' INT

wait "$HAPROXY_PID"
kill "$APP_PID" "$GRPC_PID" 2>/dev/null || true
wait "$APP_PID" 2>/dev/null || true
wait "$GRPC_PID" 2>/dev/null || true
