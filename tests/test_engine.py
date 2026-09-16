"""openwiki-server MVP 冒烟与语义测试：domain / 存储 / application / 五面接口。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openwiki_engine.adapters.openwiki import parse_okf_pages
from openwiki_engine.application.service import OpenWikiService
from openwiki_engine.config import Settings
from openwiki_engine.domain.ids import normalize_title, page_id, wiki_id
from openwiki_engine.errors import InvalidParamsError, NotFoundError
from openwiki_engine.persistence.sqlite_store import SqliteWikiStore


def _settings(tmp_path) -> Settings:
    return Settings(data_dir=str(tmp_path), openwiki_enabled=False)


@pytest.fixture()
def store(tmp_path):
    return SqliteWikiStore(str(tmp_path / "test.db"), data_dir=str(tmp_path))


@pytest.fixture()
def svc(store, tmp_path):
    return OpenWikiService(store, settings=_settings(tmp_path))


def _create(svc, kb_id="kb_test_1", config=None):
    return svc.create_wiki(
        name="测试 Wiki", kb_id=kb_id, wiki_config=config or {"granularity": "page"}
    )


# ---------- storage ----------


def test_wiki_root_is_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = SqliteWikiStore(str(tmp_path / "test.db"), data_dir="data")
    root = Path(store.wiki_root("wiki_abc12345"))
    assert root.is_absolute()
    assert root == tmp_path / "data" / "wikis" / "wiki_abc12345"
    assert (root / ".openwiki" / "wiki").is_dir()
    assert (root / "sources").is_dir()


# ---------- domain ----------


def test_stable_ids():
    assert normalize_title(" 产品 手册 ") == "产品手册"
    wid = wiki_id("kb_test_1")
    assert wid.startswith("wiki_")
    assert wid == wiki_id("kb_test_1")
    pid = page_id("kb_test_1", "产品手册")
    assert pid.startswith("wiki_")
    assert pid == page_id("kb_test_1", "产品手册")


def test_wiki_config_validation(svc):
    with pytest.raises(InvalidParamsError) as exc:
        svc.create_wiki(kb_id="kb_x", wiki_config={"granularity": "bad"})
    assert exc.value.code == "200001"
    with pytest.raises(InvalidParamsError) as exc:
        svc.create_wiki(kb_id="kb_x", wiki_config={"dedup": "nope"})
    assert exc.value.code == "200001"
    with pytest.raises(InvalidParamsError) as exc:
        svc.create_wiki(kb_id="", wiki_config={})
    assert exc.value.code == "200001"


# ---------- wiki CRUD ----------


def test_create_get_list_delete(svc):
    created = _create(svc)
    assert created["wikiId"] == wiki_id("kb_test_1")
    assert created["wikiConfig"]["granularity"] == "page"
    assert svc.get_wiki(created["wikiId"])["wikiId"] == created["wikiId"]
    assert svc.list_wikis()["total"] == 1
    svc.delete_wiki(created["wikiId"])
    with pytest.raises(NotFoundError):
        svc.get_wiki(created["wikiId"])


# ---------- build / merge / 查询 ----------


def test_build_page_tree_search_stat_export(svc):
    wid = _create(svc, config={"granularity": "heading"})["wikiId"]
    result = svc.build_from_doc(
        wid,
        doc_id="doc1",
        title="产品手册",
        tags=["手册"],
        markdown="# 产品手册\n\n## 安装\n\n安装步骤说明。\n\n## 配置\n\n配置项：端口=18000。",
    )
    assert result["mode"] == "rule"
    assert result["total"] == 3  # 根页 + 安装 + 配置
    assert result["deprecated"] == 0

    tree = svc.tree(wid)
    assert tree["total"] == 1  # 只有根页
    assert tree["tree"][0]["children"][0]["title"] == "安装"

    pid = result["pages"][1]["pageId"]
    detail = svc.page(wid, page_id_value=pid)
    assert detail["page"]["title"] == "安装"
    assert detail["page"]["sourceDocs"] == ["doc1"]

    hits = svc.search(wid, q="安装")
    assert hits["total"] >= 1
    assert hits["items"][0]["pageId"] == pid
    assert hits["items"][0]["score"] >= 10.0

    stat = svc.stat(wid)
    assert stat["active"] == 3
    assert stat["tags"]["手册"] == 3

    out = svc.export(wid, format="jsonl")
    lines = [json.loads(line) for line in out["content"].splitlines()]
    assert len(lines) == 3
    out_json = svc.export(wid, format="json")
    assert len(json.loads(out_json["content"])["pages"]) == 3


def test_merge_and_deprecate(svc):
    wid = _create(svc)["wikiId"]
    svc.build_from_doc(wid, doc_id="doc1", title="页面A", markdown="正文一。")
    svc.build_from_doc(
        wid, doc_id="doc2", title="页面A", markdown="正文二。", tags=["补充"]
    )
    page = svc.tree(wid)["tree"][0]
    assert page["title"] == "页面A"
    detail = svc.page(wid, page_id_value=page["pageId"])["page"]
    assert detail["sourceDocs"] == ["doc1", "doc2"]
    assert detail["tags"] == ["补充"]

    svc.build_from_doc(wid, doc_id="doc3", title="独立页", markdown="独立正文。")
    deprecated = svc.deprecate_doc(wid, doc_id="doc3")
    assert deprecated["deprecated"] == 1
    assert svc.search(wid, q="独立页")["total"] == 0
    # doc1 专属且未再构建 → 页面A 仍活跃（doc2 仍贡献）
    deprecated = svc.deprecate_doc(wid, doc_id="doc1")
    assert deprecated["deprecated"] == 0


def test_dedup_overwrite_skip(svc):
    wid = _create(svc, config={"granularity": "page", "dedup": "skip"})["wikiId"]
    svc.build_from_doc(wid, doc_id="doc1", title="页面A", markdown="正文一。")
    svc.build_from_doc(wid, doc_id="doc2", title="页面A", markdown="正文二。")
    detail = svc.page(wid, page_id_value=svc.tree(wid)["tree"][0]["pageId"])["page"]
    assert detail["markdown"] == "正文一。"  # skip 保留旧页

    wid2 = _create(svc, kb_id="kb_overwrite", config={"granularity": "page", "dedup": "overwrite"})["wikiId"]
    svc.build_from_doc(wid2, doc_id="doc1", title="页面B", markdown="旧正文。")
    svc.build_from_doc(wid2, doc_id="doc2", title="页面B", markdown="新正文。")
    detail = svc.page(wid2, page_id_value=svc.tree(wid2)["tree"][0]["pageId"])["page"]
    assert detail["markdown"] == "新正文。"
    assert detail["sourceDocs"] == ["doc2"]  # overwrite 不合并证据


def test_merge_records(svc):
    wid = _create(svc)["wikiId"]
    result = svc.merge_records(
        wid,
        pages=[{"title": "手工页", "markdown": "手工正文。", "tags": ["手"]}],
        doc_id="doc9",
    )
    assert result["total"] == 1
    pid = result["pages"][0]["pageId"]
    assert pid == page_id("kb_test_1", normalize_title("手工页"))


def test_fields_extraction(svc):
    wid = _create(
        svc, config={"granularity": "page", "extractFields": ["负责人", "版本"]}
    )["wikiId"]
    result = svc.build_from_doc(
        wid, doc_id="doc1", title="SOP", markdown="负责人：张三\n版本：1.2\n正文。"
    )
    fields = result["pages"][0]["fields"]
    assert fields == {"负责人": "张三", "版本": "1.2"}


def test_export_bad_format(svc):
    wid = _create(svc)["wikiId"]
    with pytest.raises(InvalidParamsError):
        svc.export(wid, format="ttl")


# ---------- OKF 解析 ----------


def test_parse_okf_pages(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "index.md").write_text("---\nokf_version: 0.2\n---\n# Index\n", encoding="utf-8")
    (wiki_dir / "concept-a.md").write_text(
        "---\ntitle: 概念A\ntype: concept\ntags: [a, b]\nsources:\n  - docId: doc1\n"
        "status: active\n---\n# 概念A\n\n正文，参见 [[概念B]]。\n",
        encoding="utf-8",
    )
    pages = parse_okf_pages(str(wiki_dir), kb_id="kb_okf")
    assert len(pages) == 1
    page = pages[0]
    assert page["title"] == "概念A"
    assert page["tags"] == ["a", "b"]
    assert page["sourceDocs"] == ["doc1"]
    assert page["links"][0]["pageId"] == page_id("kb_okf", normalize_title("概念B"))
    assert "正文" in page["markdown"]


# ---------- jobs ----------


def test_jobs(svc):
    wid = _create(svc)["wikiId"]
    job = svc.submit_job(
        "build", wid, {"docId": "doc1", "title": "任务页", "markdown": "任务正文。"}
    )
    assert job["status"] == "pending"
    result = svc.run_job(job["jobId"])
    assert result["status"] == "success"
    assert result["result"]["total"] == 1
    assert svc.get_job(job["jobId"])["status"] == "success"
    assert svc.list_jobs(wiki_id_value=wid)["total"] == 1


def test_submit_job_dispatches_to_celery(svc, monkeypatch):
    from openwiki_engine.interfaces import celery_app as celery_mod

    sent: list[tuple[str, dict]] = []

    def fake_send_task(name, **kwargs):
        sent.append((name, kwargs))

    monkeypatch.setattr(celery_mod.celery_app, "send_task", fake_send_task)
    wid = _create(svc)["wikiId"]
    job = svc.submit_job(
        "build", wid, {"docId": "doc1", "title": "任务页", "markdown": "任务正文。"}
    )
    assert job["status"] == "pending"
    assert len(sent) == 1
    name, kwargs = sent[0]
    assert name == "openwiki_server.build"
    assert kwargs["kwargs"]["wiki_id"] == wid
    assert kwargs["kwargs"]["job_id"] == job["jobId"]
    assert kwargs["kwargs"]["doc_id"] == "doc1"
    assert "async" not in kwargs["kwargs"]


def test_submit_job_keeps_pending_when_broker_down(svc, monkeypatch):
    from openwiki_engine.interfaces import celery_app as celery_mod

    def boom(*args, **kwargs):
        raise ConnectionRefusedError("broker 不可达")

    monkeypatch.setattr(celery_mod.celery_app, "send_task", boom)
    wid = _create(svc)["wikiId"]
    job = svc.submit_job(
        "build", wid, {"docId": "doc1", "title": "任务页", "markdown": "任务正文。"}
    )
    assert job["status"] == "pending"
    result = svc.run_job(job["jobId"])
    assert result["status"] == "success"


# ---------- HTTP ----------


def _route(app, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or []):
            return route
    raise AssertionError(f"路由不存在：{method} {path}")


def test_http_app(svc):
    """HTTP 协议面验证（环境沙箱阻断网络，采用路由直调验证 envelope 语义）。"""
    from openwiki_engine.interfaces.http_app import create_app

    app = create_app(svc)

    class _Request:
        def __init__(self, trace: str = "") -> None:
            self.headers = {"X-Trace-Id": trace} if trace else {}

    import json as _json

    def _payload(resp):
        body = resp.body if hasattr(resp, "body") else _json.dumps(resp).encode()
        return _json.loads(body)

    create_route = _route(app, "/api/v1/wiki/wikis", "POST")
    resp = create_route.endpoint(_Request("trace-1"), {"name": "HTTP Wiki", "kbId": "kb_http"})
    payload = _payload(resp)
    assert payload["traceId"] == "trace-1"
    assert payload["errCode"] == "0"
    wid = payload["data"]["wikiId"]

    build_route = _route(app, "/api/v1/wiki/wikis/{wiki_id}/build", "POST")
    resp = build_route.endpoint(_Request(), wid, {"docId": "d1", "title": "页面", "markdown": "正文。"})
    assert _payload(resp)["errCode"] == "0"

    tree_route = _route(app, "/api/v1/wiki/wikis/{wiki_id}/tree", "GET")
    resp = tree_route.endpoint(_Request(), wid, 1, 20)
    assert _payload(resp)["data"]["total"] == 1

    stat_route = _route(app, "/api/v1/wiki/wikis/{wiki_id}/stat", "GET")
    resp = stat_route.endpoint(_Request(), wid)
    assert _payload(resp)["data"]["pageCount"] == 1

    get_route = _route(app, "/api/v1/wiki/wikis/{wiki_id}", "GET")
    resp = get_route.endpoint(_Request(), "nope")
    assert _payload(resp)["errCode"] == "200404"

    health_route = _route(app, "/health", "GET")
    resp = health_route.endpoint()
    assert _payload(resp)["status"] == "ok"


# ---------- CLI ----------


def test_cli(svc):
    from typer.testing import CliRunner

    from openwiki_engine.interfaces import cli

    cli._service = svc
    runner = CliRunner()
    result = runner.invoke(
        cli.app, ["create", "--kb-id", "kb_cli", "--name", "CLI Wiki", "--config", '{"granularity":"page"}']
    )
    assert result.exit_code == 0, result.output
    wid = json.loads(result.output)["wikiId"]

    result = runner.invoke(
        cli.app, ["build", wid, "--doc-id", "d1", "--title", "CLI 页", "--markdown", "正文。"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["total"] == 1

    result = runner.invoke(cli.app, ["tree", wid])
    assert json.loads(result.output)["total"] == 1

    result = runner.invoke(cli.app, ["export", wid])
    assert result.exit_code == 0


# ---------- MCP ----------


def test_mcp(svc):
    from openwiki_engine.interfaces.mcp_server import _handle_request, _tool_handlers

    handlers = _tool_handlers(svc)
    init = _handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, handlers)
    assert init["result"]["serverInfo"]["name"] == "openwiki-server"

    tools = _handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, handlers)
    names = {t["name"] for t in tools["result"]["tools"]}
    assert "wiki_create" in names and "wiki_export" in names

    resp = _handle_request(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "wiki_create", "arguments": {"name": "MCP Wiki", "kbId": "kb_mcp"}}},
        handlers,
    )
    wid = json.loads(resp["result"]["content"][0]["text"])["wikiId"]
    resp = _handle_request(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "wiki_stat", "arguments": {"wikiId": wid}}},
        handlers,
    )
    assert "pageCount" in resp["result"]["content"][0]["text"]


# ---------- gRPC ----------


def test_grpc(svc):
    """gRPC 协议面验证：进程内 handler 走通 envelope 语义；沙箱允许绑定时再做真 socket 对拍。"""
    import json as _json

    from openwiki_engine.interfaces.grpc_server import Envelope, _make_handler, build_grpc_server

    try:
        server = build_grpc_server(svc)
        port = server.add_insecure_port("127.0.0.1:0")
    except RuntimeError as exc:  # 沙箱禁止绑定 socket
        pytest.skip(f"沙箱禁止 gRPC 端口绑定：{exc}")

    req = Envelope()
    req.trace_id = "t-grpc"
    req.data_json = _json.dumps({"params": {"name": "gRPC Wiki", "kbId": "kb_grpc"}})
    resp = _make_handler("CreateWiki", svc)(req, None)
    assert resp.err_code == "0"
    wid = _json.loads(resp.data_json)["wikiId"]

    req.data_json = _json.dumps({"params": {"wikiId": wid, "docId": "d1", "title": "gRPC 页", "markdown": "正文。"}})
    resp = _make_handler("BuildWiki", svc)(req, None)
    assert resp.err_code == "0"

    req.data_json = _json.dumps({"params": {"wikiId": "nope"}})
    resp = _make_handler("Stat", svc)(req, None)
    assert resp.err_code == "200404"

    server.start()
    try:
        from openwiki_engine.interfaces.grpc_server import grpc_client

        client = grpc_client("127.0.0.1", port)
        resp = client("CreateWiki", {"name": "gRPC Wiki", "kbId": "kb_grpc2"})
        assert resp["errCode"] == "0"
    finally:
        server.stop(0)


# ---------- Celery ----------


def test_celery_tasks(tmp_path):
    import os

    from openwiki_engine import runtime
    from openwiki_engine.interfaces.celery_app import build_task

    os.environ["OPENWIKI_SERVER_OPENWIKI"] = "0"
    runtime.reset_runtime()
    try:
        rt_svc = runtime.get_service(str(tmp_path / "celery.db"))
        wid = rt_svc.create_wiki(name="Celery Wiki", kb_id="kb_celery")["wikiId"]
        job = rt_svc.submit_job("build", wid, {"docId": "d1", "title": "任务页", "markdown": "正文。"})
        result = build_task.run(wid, doc_id="d1", title="任务页", markdown="正文。", job_id=job["jobId"])
        assert result["total"] == 1
        assert rt_svc.get_job(job["jobId"])["status"] == "success"
    finally:
        os.environ.pop("OPENWIKI_SERVER_OPENWIKI", None)
        runtime.reset_runtime()


def test_celery_task_failure_marks_job_failed(tmp_path):
    """任务抛异常时必须把作业落 failed + error：否则作业永远停在 pending，调用方只能靠轮询超时猜。"""
    import os

    from openwiki_engine import runtime
    from openwiki_engine.errors import NotFoundError
    from openwiki_engine.interfaces.celery_app import build_task

    os.environ["OPENWIKI_SERVER_OPENWIKI"] = "0"
    runtime.reset_runtime()
    try:
        rt_svc = runtime.get_service(str(tmp_path / "celery-fail.db"))
        job = rt_svc.submit_job(
            "build", "wiki_missing", {"docId": "d1", "title": "任务页", "markdown": "正文。"}
        )
        with pytest.raises(NotFoundError):
            build_task.run(
                "wiki_missing", doc_id="d1", title="任务页", markdown="正文。", job_id=job["jobId"]
            )
        stored = rt_svc.get_job(job["jobId"])
        assert stored["status"] == "failed"
        assert stored["error"]
        assert stored["result"] is None
    finally:
        os.environ.pop("OPENWIKI_SERVER_OPENWIKI", None)
        runtime.reset_runtime()


def test_parse_okf_pages_datetime_fields(tmp_path) -> None:
    """OKF front matter 中的 YAML 日期应归一化为 ISO 字符串（否则响应序列化 500）。"""
    from openwiki_engine.adapters.openwiki import parse_okf_pages

    wiki_dir = tmp_path / ".openwiki" / "wiki"
    wiki_dir.mkdir(parents=True)
    (wiki_dir / "p.md").write_text(
        "---\ntitle: 页面\nupdated: 2026-09-01T10:00:00+08:00\nseen: 2026-09-01\n---\n正文",
        encoding="utf-8",
    )
    pages = parse_okf_pages(str(wiki_dir), kb_id="kb-1")
    assert pages
    fields = pages[0]["fields"]
    assert fields["updated"] == "2026-09-01T10:00:00+08:00"
    assert fields["seen"] == "2026-09-01"


def test_http_response_serializes_datetime() -> None:
    """HTTP envelope 兜底序列化：datetime 值不再导致 500。"""
    from datetime import datetime

    from openwiki_engine.interfaces.http_app import _JsonResponse

    resp = _JsonResponse({"updated": datetime(2026, 9, 1, 10, 30, 0)})
    assert b'"2026-09-01T10:30:00"' in resp.body
