from __future__ import annotations

import asyncio

import httpx

from openwiki_server_sdk import AsyncOpenWikiServerClient
from openwiki_server_sdk.errors import OpenWikiServerNotFoundError

SUCCESS_BODY = {"traceId": "123", "errCode": "0", "errMsg": "", "data": {}}


def run(coro):
    return asyncio.run(coro)


def make_client(handler, **kwargs) -> AsyncOpenWikiServerClient:
    kwargs.setdefault("token", "secret-token")
    return AsyncOpenWikiServerClient(
        "http://ow.test",
        http_client=httpx.AsyncClient(transport=handler, timeout=1),
        **kwargs,
    )


def test_async_request_success():
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, json=SUCCESS_BODY)))

    async def scenario():
        envelope = await client.request("GET", "/api/v1/wiki/wikis")
        return envelope

    envelope = run(scenario())
    assert envelope.ok
    client.close()


def test_async_business_error_raises():
    body = {"traceId": "1", "errCode": "200404", "errMsg": "不存在", "data": None}
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, json=body)))

    async def scenario():
        await client.request("GET", "/api/v1/wiki/wikis/w_1")

    try:
        run(scenario())
        assert False, "should raise"
    except OpenWikiServerNotFoundError as exc:
        assert exc.err_code == "200404"
    client.close()


def test_async_wiki_domain_flow():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/wikis"):
            data = {"wikiId": "w1", "kbId": "kb1", "name": "异步"}
        elif path.endswith("/tree"):
            data = {"kbId": "kb1", "total": 0, "tree": []}
        elif path.endswith("/stat"):
            data = {"wikiId": "w1", "kbId": "kb1", "pageCount": 0, "active": 0, "tags": {}}
        else:
            data = {}
        return httpx.Response(200, json={"traceId": "1", "errCode": "0", "errMsg": "", "data": data})

    client = make_client(httpx.MockTransport(handler))

    async def scenario():
        wiki = await client.wikis.create(kbId="kb1", name="异步")
        tree = await client.wikis.tree(wiki.wikiId)
        stat = await client.wikis.stat(wiki.wikiId)
        await client.wikis.delete(wiki.wikiId)
        return wiki, tree, stat

    wiki, tree, stat = run(scenario())
    assert wiki.wikiId == "w1"
    assert tree.total == 0
    assert stat.pageCount == 0
    client.close()


def test_async_context_manager():
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, json=SUCCESS_BODY)))

    async def scenario():
        async with client as c:
            envelope = await c.request("GET", "/api/v1/wiki/wikis")
            return envelope.ok

    assert run(scenario()) is True
