from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value not in ("0", "false", "False", "no", "off")


@dataclass(frozen=True)
class Settings:
    """引擎配置：环境变量优先，缺省使用内置默认值。"""

    data_dir: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_DATA_DIR", "data"))
    db_path: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_DB_PATH", ""))
    http_host: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_HTTP_HOST", "0.0.0.0"))
    http_port: int = field(default_factory=lambda: int(_env("OPENWIKI_SERVER_HTTP_PORT", "18011")))
    grpc_host: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_GRPC_HOST", "0.0.0.0"))
    grpc_port: int = field(default_factory=lambda: int(_env("OPENWIKI_SERVER_GRPC_PORT", "50052")))
    celery_broker: str = field(
        default_factory=lambda: _env("OPENWIKI_SERVER_CELERY_BROKER", "redis://localhost:6379/0")
    )
    celery_backend: str = field(
        default_factory=lambda: _env("OPENWIKI_SERVER_CELERY_BACKEND", "redis://localhost:6379/0")
    )
    mcp_transport: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_MCP_TRANSPORT", "stdio"))
    log_level: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_LOG_LEVEL", "INFO"))
    openwiki_bin: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_OPENWIKI_BIN", ""))
    openwiki_enabled: bool = field(
        default_factory=lambda: _env_bool("OPENWIKI_SERVER_OPENWIKI", True)
    )
    openwiki_provider: str = field(
        default_factory=lambda: _env("OPENWIKI_SERVER_PROVIDER", "openai")
    )
    openwiki_model_id: str = field(default_factory=lambda: _env("OPENWIKI_SERVER_MODEL_ID", ""))
    openwiki_update_timeout: int = field(
        default_factory=lambda: int(_env("OPENWIKI_SERVER_UPDATE_TIMEOUT", "600"))
    )

    @property
    def resolved_db_path(self) -> str:
        if self.db_path:
            return self.db_path
        data_dir = Path(self.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        return str(data_dir / "engine.db")

    def wiki_root(self, wiki_id: str) -> str:
        """wiki 实例根目录：{data_dir}/wikis/{wiki_id}/（含 .openwiki/wiki 与 sources/）。"""
        root = Path(self.data_dir) / "wikis" / wiki_id
        root.mkdir(parents=True, exist_ok=True)
        (root / ".openwiki" / "wiki").mkdir(parents=True, exist_ok=True)
        (root / "sources").mkdir(parents=True, exist_ok=True)
        return str(root)

    def openwiki_bin_resolved(self) -> str:
        """解析 openwiki 可执行文件路径：env 指定 > PATH > 项目内 node_modules。"""
        if self.openwiki_bin:
            return self.openwiki_bin
        found = shutil.which("openwiki")
        if found:
            return found
        candidates = [
            Path(__file__).resolve().parents[2] / "node_modules" / ".bin" / "openwiki",
            Path.cwd() / "node_modules" / ".bin" / "openwiki",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return "openwiki"
