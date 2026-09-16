"""core 回写适配层用例：开关、契约字段、HTTP 形状（路径/鉴权头/载荷）、错误降级。

用本机 `http.server` 起桩（零新依赖），断言**实际发出的请求**与 core `§2.5` 契约一致——
这正是 G-05（`format=ttl` 跨仓漂移）那类问题的拦阻点。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from openwiki_engine.adapters import core_writeback


class _Stub:
    def __init__(self, *, err_code: str = "000000") -> None:
        self.requests: list[dict] = []
        self.err_code = err_code


@pytest.fixture()
def stub(monkeypatch) -> _Stub:
    state = _Stub()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server 协议命名
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8")
            state.requests.append(
                {
                    "path": self.path,
                    "token": self.headers.get("X-Internal-Token"),
                    "json": json.loads(raw),
                }
            )
            body = json.dumps(
                {
                    "errCode": state.err_code,
                    "errMsg": "" if state.err_code == "000000" else "回写被拒",
                    "data": {"created": 1, "mode": "openwiki"} if state.err_code == "000000" else {},
                    "traceId": "17570000000000000000001",
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # 静音
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("IKC_CORE_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("IKC_CORE_ADMIN_TOKEN", "internal-admin-token")
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


_PAGE = {
    "pageId": "wiki_1",
    "wikiId": "wiki_1",
    "kbId": "kb_1",
    "docId": "doc_1",
    "title": "首页",
    "level": 1,
    "parentPageId": "",
    "stableKey": "首页",
    "fields": {"owner": "u-1"},
    "tags": ["a"],
    "markdown": "# 首页",
    "links": [{"title": "安装", "pageId": "wiki_2"}],
    "sourceDocs": ["doc_1"],
    "status": "active",
    "contentState": "draft",
    "createdAt": "2026-09-16T00:00:00Z",
    "updatedAt": "2026-09-16T00:00:00Z",
}


def test_disabled_without_base_url(monkeypatch) -> None:
    monkeypatch.delenv("IKC_CORE_BASE_URL", raising=False)
    assert core_writeback.writeback_enabled() is False
    assert core_writeback.write_pages("kb_1", pages=[_PAGE]) is None


def test_disabled_by_switch(monkeypatch, stub) -> None:
    monkeypatch.setenv("IKC_CORE_WRITEBACK", "0")
    assert core_writeback.writeback_enabled() is False
    assert core_writeback.write_pages("kb_1", pages=[_PAGE]) is None
    assert stub.requests == []


def test_write_pages_contract_and_payload(stub) -> None:
    result = core_writeback.write_pages(
        "kb_1",
        doc_id="doc_1",
        pages=[_PAGE],
        dedup="merge",
        mode="openwiki",
        task_id="task-1",
    )
    assert result is not None and result["ok"] is True and result["created"] == 1
    assert len(stub.requests) == 1
    sent = stub.requests[0]
    assert sent["path"] == "/internal/wiki/build"
    assert sent["token"] == "internal-admin-token"
    body = sent["json"]
    # 契约字段（camelCase；core extra=forbid，多余键会被 100001 拒收）
    assert set(body) == {
        "kbId",
        "docId",
        "pages",
        "dedup",
        "mode",
        "taskId",
        "engine",
        "engineVersion",
    }
    assert body["kbId"] == "kb_1" and body["dedup"] == "merge" and body["mode"] == "openwiki"
    assert body["engine"] == "openwiki-server" and body["engineVersion"]
    page = body["pages"][0]
    # 只投递 core 契约字段（多余键会被 core extra=forbid 拒收为 100001）
    assert set(page) <= set(core_writeback._PAGE_FIELDS)
    assert {"title", "stableKey", "markdown", "links", "sourceDocs"} <= set(page)
    # 本地字段不外投；contentState 不在契约内（产物恒 draft 由 core 决定）
    assert "contentState" not in page and "createdAt" not in page and "pageId" not in page
    assert page["stableKey"] == "首页" and page["sourceDocs"] == ["doc_1"]


def test_page_payload_drops_local_fields() -> None:
    payload = core_writeback.page_payload(_PAGE)
    assert "pageId" not in payload and "status" not in payload
    assert payload["links"] == [{"title": "安装", "pageId": "wiki_2"}]


def test_error_code_degrades_without_raising(stub) -> None:
    stub.err_code = "100401"
    result = core_writeback.write_pages("kb_1", doc_id="doc_1", pages=[_PAGE])
    assert result is not None and result["ok"] is False
    assert "100401" in result["error"]


def test_unreachable_core_degrades(monkeypatch) -> None:
    monkeypatch.setenv("IKC_CORE_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("IKC_CORE_WRITEBACK_TIMEOUT", "1")
    result = core_writeback.write_pages("kb_1", pages=[_PAGE])
    assert result is not None and result["ok"] is False
    assert result["endpoint"] == "wiki/build"


def test_engine_version_matches_pyproject() -> None:
    """版本漂移护栏：回写审计里的 engineVersion 必须等于本仓 pyproject 声明。"""
    import tomllib
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    declared = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert core_writeback.ENGINE_VERSION == declared["project"]["version"]
