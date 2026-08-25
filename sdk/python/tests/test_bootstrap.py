from __future__ import annotations

import httpx

from openwiki_server_sdk import async_client_from_env, client_from_env

SUCCESS_BODY = {"traceId": "1", "errCode": "0", "errMsg": "", "data": {}}


def test_client_from_env_default_base_url(monkeypatch):
    monkeypatch.delenv("OPENWIKI_SERVER_BASE_URL", raising=False)
    client = client_from_env(http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=SUCCESS_BODY))))
    assert client._transport.base_url == "http://127.0.0.1:18011"
    assert client._transport.has_token is False
    client.close()


def test_client_from_env_reads_env(monkeypatch):
    monkeypatch.setenv("OPENWIKI_SERVER_BASE_URL", "http://127.0.0.1:18111")
    monkeypatch.setenv("OPENWIKI_SERVER_TOKEN", "env-token")
    monkeypatch.setenv("OPENWIKI_SERVER_USER_ID", "u1")
    monkeypatch.setenv("OPENWIKI_SERVER_TENANT_ID", "t1")
    monkeypatch.setenv("OPENWIKI_SERVER_ROLES", "km_admin,viewer")
    client = client_from_env(http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=SUCCESS_BODY))))
    assert client._transport.base_url == "http://127.0.0.1:18111"
    assert client._transport.has_token is True
    identity = client._transport._identity
    assert identity.user_id == "u1"
    assert identity.roles == ["km_admin", "viewer"]
    client.close()


def test_client_from_env_explicit_overrides(monkeypatch):
    monkeypatch.setenv("OPENWIKI_SERVER_BASE_URL", "http://env:1")
    client = client_from_env(
        base_url="http://explicit:2",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=SUCCESS_BODY))),
    )
    assert client._transport.base_url == "http://explicit:2"
    client.close()


def test_async_client_from_env(monkeypatch):
    monkeypatch.setenv("OPENWIKI_SERVER_BASE_URL", "http://127.0.0.1:18111")
    client = async_client_from_env(http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=SUCCESS_BODY))))
    assert client._transport.base_url == "http://127.0.0.1:18111"
    client.close()
