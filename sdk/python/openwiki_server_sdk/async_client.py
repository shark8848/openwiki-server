from __future__ import annotations

from typing import Any

import httpx

from .envelope import Envelope
from .headers import CallerIdentity
from .models.wiki import (
    BuildResult,
    JobListData,
    WikiExport,
    WikiJob,
    WikiListData,
    WikiMeta,
    WikiOpResult,
    WikiPageData,
    WikiSearchData,
    WikiStat,
    WikiTreeData,
)
from .transport_async import AsyncTransport


class AsyncOpenWikiServerClient:
    """OpenWiki Server 独立承载服务异步客户端；与同步客户端共享模型与错误映射。"""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: tuple[float, float] | float | None = None,
        max_retries: int = 2,
        identity: CallerIdentity | None = None,
        extra_headers: dict[str, str] | None = None,
        trace_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._transport = AsyncTransport(
            base_url=base_url,
            token=token,
            timeout=timeout,
            max_retries=max_retries,
            identity=identity,
            extra_headers=extra_headers,
            trace_id=trace_id,
            http_client=http_client,
        )
        self.wikis = AsyncWikiClient(self)
        self.jobs = AsyncJobsClient(self)

    async def request(
        self,
        method: str,
        path: str,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Envelope:
        """低层业务调用：errCode != 0 时抛对应异常。"""
        return await self._transport.request(
            method, path, path_params=path_params, params=params, body=body, raise_for_error=True
        )

    async def raw(
        self,
        method: str,
        path: str,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Envelope:
        """逃生口：返回原始统一响应壳，业务错误码不抛异常。"""
        return await self._transport.request(
            method, path, path_params=path_params, params=params, body=body, raise_for_error=False
        )

    async def fetch_openapi(self) -> list[dict[str, Any]]:
        """运行时自检入口：拉取 FastAPI 自动生成的 /openapi.json（接口目录）。"""
        return await self._transport.get_json("/openapi.json")

    async def close(self) -> None:
        await self._transport.close()

    async def __aenter__(self) -> "AsyncOpenWikiServerClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    def __repr__(self) -> str:
        token_state = "<set>" if self._transport.has_token else "None"
        return f"AsyncOpenWikiServerClient(base_url={self._transport.base_url!r}, token={token_state})"


class AsyncWikiClient:
    """Wiki 域异步客户端：create / list / get / delete / tree / page / search / stat / export /
    build / merge / deprecate_doc / update / ingest。"""

    def __init__(self, client: AsyncOpenWikiServerClient) -> None:
        self._client = client

    async def create(
        self,
        *,
        kbId: str,
        name: str = "",
        wikiId: str = "",
        tenantId: str = "",
        ownerId: str = "",
        wikiConfig: dict[str, Any] | None = None,
    ) -> WikiMeta:
        body: dict[str, Any] = {"kbId": kbId}
        if name:
            body["name"] = name
        if wikiId:
            body["wikiId"] = wikiId
        if tenantId:
            body["tenantId"] = tenantId
        if ownerId:
            body["ownerId"] = ownerId
        if wikiConfig:
            body["wikiConfig"] = dict(wikiConfig)
        envelope = await self._client.request("POST", "/api/v1/wiki/wikis", body=body)
        return WikiMeta.from_dict(envelope.data or {})

    async def list(self, *, tenantId: str = "", ownerId: str = "") -> WikiListData:
        params: dict[str, str] = {}
        if tenantId:
            params["tenantId"] = tenantId
        if ownerId:
            params["ownerId"] = ownerId
        envelope = await self._client.request("GET", "/api/v1/wiki/wikis", params=params)
        return WikiListData.from_dict(envelope.data or {})

    async def get(self, wikiId: str) -> WikiMeta:
        envelope = await self._client.request("GET", "/api/v1/wiki/wikis/{wiki_id}", path_params={"wiki_id": wikiId})
        return WikiMeta.from_dict(envelope.data or {})

    async def delete(self, wikiId: str) -> WikiOpResult:
        envelope = await self._client.request("DELETE", "/api/v1/wiki/wikis/{wiki_id}", path_params={"wiki_id": wikiId})
        return WikiOpResult.from_dict(envelope.data or {})

    async def tree(self, wikiId: str, *, page: int = 1, pageSize: int = 20) -> WikiTreeData:
        envelope = await self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/tree",
            path_params={"wiki_id": wikiId},
            params={"page": page, "pageSize": pageSize},
        )
        return WikiTreeData.from_dict(envelope.data or {})

    async def page(self, wikiId: str, pageId: str) -> WikiPageData:
        envelope = await self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/page",
            path_params={"wiki_id": wikiId},
            params={"pageId": pageId},
        )
        return WikiPageData.from_dict(envelope.data or {})

    async def search(self, wikiId: str, *, q: str = "", tag: str = "", limit: int = 20) -> WikiSearchData:
        params: dict[str, Any] = {"limit": limit}
        if q:
            params["q"] = q
        if tag:
            params["tag"] = tag
        envelope = await self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/search",
            path_params={"wiki_id": wikiId},
            params=params,
        )
        return WikiSearchData.from_dict(envelope.data or {})

    async def stat(self, wikiId: str) -> WikiStat:
        envelope = await self._client.request("GET", "/api/v1/wiki/wikis/{wiki_id}/stat", path_params={"wiki_id": wikiId})
        return WikiStat.from_dict(envelope.data or {})

    async def export(self, wikiId: str, *, format: str = "jsonl") -> WikiExport:
        envelope = await self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/export",
            path_params={"wiki_id": wikiId},
            params={"format": format},
        )
        return WikiExport.from_dict(envelope.data or {})

    async def build(
        self,
        wikiId: str,
        *,
        docId: str = "",
        title: str = "",
        tags: list[str] | None = None,
        markdown: str = "",
        wikiConfig: dict[str, Any] | None = None,
        async_: bool = False,
    ) -> BuildResult | WikiJob:
        body: dict[str, Any] = {}
        if docId:
            body["docId"] = docId
        if title:
            body["title"] = title
        if tags:
            body["tags"] = list(tags)
        if markdown:
            body["markdown"] = markdown
        if wikiConfig:
            body["wikiConfig"] = dict(wikiConfig)
        if async_:
            body["async"] = "1"
        envelope = await self._client.request(
            "POST", "/api/v1/wiki/wikis/{wiki_id}/build", path_params={"wiki_id": wikiId}, body=body
        )
        if async_:
            return WikiJob.from_dict(envelope.data or {})
        return BuildResult.from_dict(envelope.data or {})

    async def merge(
        self,
        wikiId: str,
        *,
        pages: list[dict[str, Any]] | None = None,
        docId: str = "",
    ) -> BuildResult:
        body: dict[str, Any] = {"pages": list(pages or [])}
        if docId:
            body["docId"] = docId
        envelope = await self._client.request(
            "POST", "/api/v1/wiki/wikis/{wiki_id}/merge", path_params={"wiki_id": wikiId}, body=body
        )
        return BuildResult.from_dict(envelope.data or {})

    async def deprecate_doc(self, wikiId: str, *, docId: str) -> WikiOpResult:
        envelope = await self._client.request(
            "POST",
            "/api/v1/wiki/wikis/{wiki_id}/deprecate-doc",
            path_params={"wiki_id": wikiId},
            body={"docId": docId},
        )
        return WikiOpResult.from_dict(envelope.data or {})

    async def update(self, wikiId: str, *, message: str = "") -> WikiOpResult:
        body: dict[str, Any] = {}
        if message:
            body["message"] = message
        envelope = await self._client.request(
            "POST", "/api/v1/wiki/wikis/{wiki_id}/update", path_params={"wiki_id": wikiId}, body=body
        )
        return WikiOpResult.from_dict(envelope.data or {})

    async def ingest(self, wikiId: str, *, connector: str) -> WikiOpResult:
        envelope = await self._client.request(
            "POST",
            "/api/v1/wiki/wikis/{wiki_id}/ingest",
            path_params={"wiki_id": wikiId},
            body={"connector": connector},
        )
        return WikiOpResult.from_dict(envelope.data or {})


class AsyncJobsClient:
    """异步任务域客户端：run / get / list。"""

    def __init__(self, client: AsyncOpenWikiServerClient) -> None:
        self._client = client

    async def run(self, jobId: str) -> WikiJob:
        envelope = await self._client.request(
            "POST", "/api/v1/wiki/jobs/{job_id}/run", path_params={"job_id": jobId}
        )
        return WikiJob.from_dict(envelope.data or {})

    async def get(self, jobId: str) -> WikiJob:
        envelope = await self._client.request("GET", "/api/v1/wiki/jobs/{job_id}", path_params={"job_id": jobId})
        return WikiJob.from_dict(envelope.data or {})

    async def list(self, *, wikiId: str = "", limit: int = 20) -> JobListData:
        params: dict[str, Any] = {"limit": limit}
        if wikiId:
            params["wikiId"] = wikiId
        envelope = await self._client.request("GET", "/api/v1/wiki/jobs", params=params)
        return JobListData.from_dict(envelope.data or {})
