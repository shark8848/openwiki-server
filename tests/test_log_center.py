"""IKC Log Center 集成测试（参考 PyUploadX tests/unit/test_log_center.py）。"""

from __future__ import annotations

import json
import logging

import pytest

from openwiki_engine.config import LogCenterSettings, Settings
from openwiki_engine.logging_setup import JsonFormatter, configure_logging, request_id_var


def _http_handlers():
    return [
        handler
        for handler in logging.getLogger().handlers
        if type(handler).__name__ == "HttpLogHandler"
    ]


def test_payload_json_matches_console_format() -> None:
    record = logging.LogRecord(
        name="openwiki_engine.application.service",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="build ok",
        args=(),
        exc_info=None,
    )
    record.extra_fields = {"wiki_id": "w-1", "duration_ms": 12}
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "openwiki_engine.application.service"
    assert payload["message"] == "build ok"
    assert payload["wiki_id"] == "w-1"
    assert payload["duration_ms"] == 12


def test_payload_includes_request_id_from_context() -> None:
    record = logging.LogRecord(
        name="openwiki_engine.core",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ctx",
        args=(),
        exc_info=None,
    )
    token = request_id_var.set("req-abc")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-abc"


def test_attach_http_handler_when_enabled(monkeypatch) -> None:
    pytest.importorskip("log_center_sdk")
    import log_center_sdk.handlers as handlers_module

    captured: list[dict] = []

    class StubHttpHandler(logging.Handler):
        def __init__(self, **kwargs) -> None:
            super().__init__()
            captured.append(kwargs)

        def emit(self, record: logging.LogRecord) -> None:
            pass

    monkeypatch.setattr(handlers_module, "HttpLogHandler", StubHttpHandler)
    configure_logging(
        level="INFO",
        fmt="json",
        log_center=LogCenterSettings(
            enabled=True,
            url="http://log-center:9315",
            token="sk-test",
            batch_size=10,
        ),
    )
    assert captured == [
        {
            "endpoint": "http://log-center:9315",
            "timeout": 2.0,
            "queue_size": 1000,
            "batch_size": 10,
            "token": "sk-test",
        }
    ]


def test_disabled_or_missing_url_skips_attachment() -> None:
    configure_logging(
        level="INFO",
        fmt="json",
        log_center=LogCenterSettings(enabled=False, url="http://log-center:9315"),
    )
    assert _http_handlers() == []
    configure_logging(
        level="INFO",
        fmt="json",
        log_center=LogCenterSettings(enabled=True, url=None),
    )
    assert _http_handlers() == []


def test_settings_log_center_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENWIKI_SERVER_LOG_CENTER_ENABLED", "1")
    monkeypatch.setenv("OPENWIKI_SERVER_LOG_CENTER_URL", "http://log-center:9315")
    monkeypatch.setenv("OPENWIKI_SERVER_LOG_CENTER_TOKEN", "sk-123")
    settings = Settings()
    assert settings.log_center.enabled
    assert settings.log_center.url == "http://log-center:9315"
    assert settings.log_center.token == "sk-123"
