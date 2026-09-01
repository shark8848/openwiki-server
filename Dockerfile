#
# openwiki-server 镜像（单阶段，单镜像内含 HAProxy 代理层 + Node openwiki 内核）：
#   python:3.12-slim 运行引擎 + apt 安装 HAProxy + 官方 tarball 安装 Node 22 + npm 全局安装
#   OpenWiki 内核（openwiki 0.3.3 要求 Node >= 22）。
#
# 拓扑（容器内）：client -> HAProxy(:8080 HTTP / :50052 gRPC / :8404 stats)
#                          -> uvicorn(127.0.0.1:18011，仅回环)
#                          -> gRPC(127.0.0.1:50052，仅回环)
# 引擎进程只监听容器回环，对外唯一入口为 HAProxy（参考 open-ikc 同款单镜像代理拓扑）。
#
# 说明：Node 走 nodejs.org 官方二进制 tarball（不依赖 Docker Hub 的 node 基础镜像），
#       网络受限环境构建更稳；版本由 ARG 固定保证可复现。
#
# 配置模板 /etc/haproxy/haproxy.cfg.tmpl 由入口脚本 envsubst 渲染
# （stats 账号/密码取自 HAPROXY_STATS_USER / HAPROXY_STATS_PASSWORD）。

FROM python:3.12-slim

# HAProxy 反向代理 + envsubst（渲染 stats 账号/密码）+ node 运行库 + 下载/解压工具
RUN apt-get update \
    && apt-get install -y --no-install-recommends haproxy gettext libstdc++6 \
       curl ca-certificates xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Node.js 运行时（官方二进制 tarball，含 npm/npx/corepack）
ARG NODE_VERSION=22.14.0
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
      | tar -xJ -C /usr/local --strip-components=1 \
    && node -v && npm -v

# OpenWiki 内核（Node CLI，全局安装；引擎通过 shutil.which 在 PATH 上解析）
ARG OPENWIKI_VERSION=0.3.3
RUN npm install -g "openwiki@${OPENWIKI_VERSION}" \
    && npm ls -g openwiki

WORKDIR /app
COPY pyproject.toml README.md ./
COPY openwiki_engine/ ./openwiki_engine/
# 契约与参考文档随镜像打包，便于容器内排障
COPY proto/ ./proto/
COPY docs/ ./docs/
COPY config/ ./config/
RUN pip install --no-cache-dir ".[log-center]"

# HAProxy 代理层：配置模板 + 入口脚本（渲染配置后同进程拉起 uvicorn + gRPC + haproxy）
COPY docker/haproxy.cfg /etc/haproxy/haproxy.cfg.tmpl
COPY docker/entrypoint.sh /usr/local/bin/openwiki-entrypoint.sh

# 非 root 运行；uid 1000 与常见宿主机用户对齐，便于挂载 data 卷
RUN useradd --uid 1000 --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app \
    && chmod +x /usr/local/bin/openwiki-entrypoint.sh

USER appuser

# 仅暴露 HAProxy 入口（HTTP + gRPC + stats）；引擎 18011/50052 只在容器回环内
EXPOSE 8080 50052 8404

ENTRYPOINT ["/usr/local/bin/openwiki-entrypoint.sh"]
