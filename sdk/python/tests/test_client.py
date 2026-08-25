from __future__ import annotations

import httpx
import pytest

from openwiki_server_sdk import CallerIdentity, OpenWikiServerClient
from openwiki_server_sdk.errors import (
    OpenWikiServerHTTPStatusError,
    OpenWikiServerNotFoundError,
    OpenWikiServerValidationError,
)

SUCCESS_BODY = {"traceId": "123", "errCode": "0", "errMsg": "", "data": {}}


def make_client(handler: httpx.MockTransport, **kwargs) -> OpenWikiServerClient:
    kwargs.setdefault("token", "secret-token")
    return OpenWikiServerClient(
        "http://ow.test",
        http_client=httpx.Client(transport=handler, timeout=1),
        **kwargs,
    )


def test_request_returns_envelope_on_success():
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, json=SUCCESS_BODY)))
    envelope = client.request("GET", "/api/v1/wiki/wikis")
    assert envelope.ok
    assert envelope.trace_id == "123"
    client.close()


def test_request_raises_mapped_exception_on_business_error():
    body = {"traceId": "1", "errCode": "200001", "errMsg": "kbId 必填", "data": None}
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    with pytest.raises(OpenWikiServerValidationError):
        client.request("POST", "/api/v1/wiki/wikis", body={"name": "x"})
    client.close()


def test_raw_returns_envelope_without_raising():
    body = {"traceId": "1", "errCode": "200404", "errMsg": "不存在", "data": None}
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    envelope = client.raw("GET", "/api/v1/wiki/wikis/w_1")
    assert envelope.err_code == "200404"
    client.close()


def test_http_error_with_envelope_raises_mapped_exception():
    body = {"traceId": "1", "errCode": "200404", "errMsg": "资源不存在", "data": None}
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(404, json=body)))
    with pytest.raises(OpenWikiServerNotFoundError):
        client.request("GET", "/api/v1/wiki/wikis/w_missing")
    client.close()


def test_http_error_without_envelope_raises_status_error():
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(500, text="oops")))
    with pytest.raises(OpenWikiServerHTTPStatusError) as exc_info:
        client.request("GET", "/api/v1/wiki/wikis")
    assert exc_info.value.status_code == 500
    client.close()


def test_path_params_are_substituted():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=SUCCESS_BODY)

    client = make_client(httpx.MockTransport(handler))
    client.request("GET", "/api/v1/wiki/wikis/{wiki_id}", path_params={"wiki_id": "w_9"})
    assert captured["url"] == "http://ow.test/api/v1/wiki/wikis/w_9"
    client.close()


def test_request_headers_sent():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        return httpx.Response(200, json=SUCCESS_BODY)

    client = make_client(
        httpx.MockTransport(handler),
        identity=CallerIdentity(user_id="u1", tenant_id="t1", roles=["km_admin"]),
    )
    client.request("GET", "/api/v1/wiki/wikis")
    headers = captured["headers"]
    assert headers["x-trace-id"]
    assert headers["authorization"] == "Bearer secret-token"
    assert headers["x-user-id"] == "u1"
    assert headers["x-tenant-id"] == "t1"
    assert headers["x-user-roles"] == "km_admin"
    client.close()


def test_wikis_create_and_list():
    created = {
        "wikiId": "wiki_abc",
        "kbId": "kb_1",
        "name": "演示",
        "wikiConfig": {"granularity": "heading"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/wiki/wikis"
        if request.method == "POST":
            return httpx.Response(200, json={"traceId": "1", "errCode": "0", "errMsg": "", "data": created})
        return httpx.Response(
            200,
            json={"traceId": "1", "errCode": "0", "errMsg": "", "data": {"total": 1, "items": [created]}},
        )

    client = make_client(httpx.MockTransport(handler))
    wiki = client.wikis.create(kbId="kb_1", name="演示", wikiConfig={"granularity": "heading"})
    assert wiki.wikiId == "wiki_abc"
    listing = client.wikis.list()
    assert listing.total == 1
    client.close()


def test_wikis_tree_page_search_stat_export():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        data = {}
        if path.endswith("/tree"):
            data = {"wikiId": "w1", "kbId": "kb1", "total": 1, "tree": [{"pageId": "p1", "title": "根", "level": 1}]}
        elif path.endswith("/page"):
            data = {"kbId": "kb1", "page": {"pageId": "p1", "title": "安装", "markdown": "# 安装"}}
        elif path.endswith("/search"):
            data = {"kbId": "kb1", "q": "安装", "total": 1, "items": [{"pageId": "p1", "title": "安装", "score": 10.0}]}
        elif path.endswith("/stat"):
            data = {"wikiId": "w1", "kbId": "kb1", "pageCount": 1, "active": 1, "tags": {}}
        elif path.endswith("/export"):
            data = {"wikiId": "w1", "kbId": "kb1", "format": "jsonl", "total": 1, "content": '{"pageId":"p1"}'}
        return httpx.Response(200, json={"traceId": "1", "errCode": "0", "errMsg": "", "data": data})

    client = make_client(httpx.MockTransport(handler))
    assert client.wikis.tree("w1").tree[0].title == "根"
    assert client.wikis.page("w1", "p1").page.title == "安装"
    assert client.wikis.search("w1", q="安装").items[0].score == 10.0
    assert client.wikis.stat("w1").pageCount == 1
    assert client.wikis.export("w1").content.startswith('{"pageId"')
    client.close()


def test_wikis_build_merge_deprecate_and_jobs():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/build") and request.url.params.get("async") is None:
            body = request.read().decode()
            if '"async":"1"' in body:
                data = {"jobId": "job_1", "wikiId": "w1", "task": "build", "status": "pending"}
            else:
                data = {"wikiId": "w1", "kbId": "kb1", "docId": "d1", "mode": "rule", "total": 1, "pages": []}
        elif path.endswith("/merge"):
            data = {"wikiId": "w1", "kbId": "kb1", "total": 1, "pages": []}
        elif path.endswith("/deprecate-doc"):
            data = {"wikiId": "w1", "kbId": "kb1", "docId": "d1", "deprecated": 1}
        elif "/jobs/" in path and path.endswith("/run"):
            data = {"jobId": "job_1", "task": "build", "status": "success", "result": {"total": 1}}
        elif path.endswith("/jobs"):
            data = {"total": 1, "items": [{"jobId": "job_1", "task": "build", "status": "success"}]}
        else:
            data = {}
        return httpx.Response(200, json={"traceId": "1", "errCode": "0", "errMsg": "", "data": data})

    client = make_client(httpx.MockTransport(handler))
    result = client.wikis.build("w1", docId="d1", title="T", markdown="# T")
    assert result.mode == "rule"

    job = client.wikis.build("w1", docId="d1", markdown="# T", async_=True)
    assert isinstance(job, object) and getattr(job, "jobId", "") == "job_1"

    merged = client.wikis.merge("w1", pages=[{"title": "P", "markdown": "正文"}])
    assert merged.total == 1

    deprecated = client.wikis.deprecate_doc("w1", docId="d1")
    assert deprecated.deprecated == 1

    run = client.jobs.run("job_1")
    assert run.status == "success"
    assert client.jobs.list(wikiId="w1").total == 1
    client.close()


def test_fetch_openapi():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"paths": {"/health": {}}})

    client = make_client(httpx.MockTransport(handler))
    catalog = client.fetch_openapi()
    assert "/health" in catalog["paths"]
    client.close()
