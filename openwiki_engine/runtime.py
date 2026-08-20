"""运行时单例：存储与服务全局共享（HTTP/gRPC/Celery/MCP/CLI 复用同一实例）。"""

from __future__ import annotations

import threading
from typing import Any

from .application.service import OpenWikiService
from .config import Settings
from .persistence.sqlite_store import SqliteWikiStore

_lock = threading.RLock()
_store: SqliteWikiStore | None = None
_service: OpenWikiService | None = None


def get_settings() -> Settings:
    return Settings()


def get_store(db_path: str | None = None) -> SqliteWikiStore:
    global _store
    with _lock:
        if _store is None:
            settings = get_settings()
            _store = SqliteWikiStore(
                db_path or settings.resolved_db_path, data_dir=settings.data_dir
            )
        return _store


def get_service(db_path: str | None = None) -> OpenWikiService:
    global _service
    with _lock:
        if _service is None:
            settings = get_settings()
            _service = OpenWikiService(get_store(db_path), settings=settings)
        return _service


def reset_runtime() -> None:
    global _store, _service
    with _lock:
        _store = None
        _service = None
