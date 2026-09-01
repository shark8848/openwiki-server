"""结构化 JSON 日志 + IKC Log Center 远程投递（HTTP POST {url}/ingest，参考 PyUploadX）。"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import LogCenterSettings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
node_id_var: ContextVar[str | None] = ContextVar("node_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(UTC).isoformat()
        payload: dict[str, Any] = {
            "ts": ts,
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for name, var in (
            ("request_id", request_id_var),
            ("trace_id", trace_id_var),
            ("node_id", node_id_var),
        ):
            value = var.get()
            if value:
                payload[name] = value
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    log_center: LogCenterSettings | None = None,
) -> None:
    """配置根 logger；启用时挂载 IKC Log Center HTTP 投递 handler（幂等重建）。"""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    if log_center is not None and log_center.enabled:
        attach_log_center_handlers(log_center)


def attach_log_center_handlers(config: LogCenterSettings) -> None:
    """尽力而为地挂载 IKC Log Center 远程投递（HTTP POST {url}/ingest）。"""
    if not config.url:
        logging.getLogger(__name__).warning(
            "log_center.enabled 为 true 但未配置 url；远程投递关闭"
        )
        return
    try:
        from log_center_sdk.handlers import HttpLogHandler
    except ImportError:
        logging.getLogger(__name__).warning(
            "未安装 ikc-log-center（pip install openwiki-server[log-center]）；远程日志投递关闭"
        )
        return
    try:
        handler = HttpLogHandler(
            endpoint=config.url,
            timeout=config.timeout_seconds,
            queue_size=config.queue_size,
            batch_size=config.batch_size,
            token=config.token or "",
        )
        handler.setFormatter(JsonFormatter())
        logging.getLogger().addHandler(handler)
        logging.getLogger(__name__).info(
            "log center HTTP 投递已挂载",
            extra={"extra_fields": {"endpoint": config.url}},
        )
    except Exception:
        logging.getLogger(__name__).exception("挂载 log center handler 失败")
