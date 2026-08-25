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
from .transport import Transport


class OpenWikiServerClient:
    """OpenWiki Server 独立承载服务同步客户端。

    覆盖服务端全部 wiki 能力：实例 CRUD / 建页加工（build/merge/deprecate/update/ingest）/
    查询（tree/page/search/stat/export）/ 异步任务（jobs）。
    """

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
        http_client: httpx.Client | None = None,
    ) -> None:
        self._transport = Transport(
            base_url=base_url,
            token=token,
            timeout=timeout,
            max_retries=max_retries,
            identity=identity,
            extra_headers=extra_headers,
            trace_id=trace_id,
            http_client=http_client,
        )
        self.wikis = WikiClient(self)
        self.jobs = JobsClient(self)

    def request(
        self,
        method: str,
        path: str,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Envelope:
        """低层业务调用：errCode != 0 时抛对应异常。"""
        return self._transport.request(
            method, path, path_params=path_params, params=params, body=body, raise_for_error=True
        )

    def raw(
        self,
        method: str,
        path: str,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Envelope:
        """逃生口：返回原始统一响应壳，业务错误码不抛异常。"""
        return self._transport.request(
            method, path, path_params=path_params, params=params, body=body, raise_for_error=False
        )

    def fetch_openapi(self) -> list[dict[str, Any]]:
        """运行时自检入口：拉取 FastAPI 自动生成的 /openapi.json（接口目录）。"""
        return self._transport.get_json("/openapi.json")

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "OpenWikiServerClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        token_state = "<set>" if self._transport.has_token else "None"
        return f"OpenWikiServerClient(base_url={self._transport.base_url!r}, token={token_state})"


class WikiClient:
    """Wiki 域客户端：create / list / get / delete / tree / page / search / stat / export /
    build / merge / deprecate_doc / update / ingest。"""

    def __init__(self, client: OpenWikiServerClient) -> None:
        self._client = client

    def create(
        self,
        *,
        kbId: str,
        name: str = "",
        wikiId: str = "",
        tenantId: str = "",
        ownerId: str = "",
        wikiConfig: dict[str, Any] | None = None,
    ) -> WikiMeta:
        """创建 wiki 实例；wikiId 缺省由服务端从 kbId 稳定派生。"""
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
        envelope = self._client.request("POST", "/api/v1/wiki/wikis", body=body)
        return WikiMeta.from_dict(envelope.data or {})

    def list(self, *, tenantId: str = "", ownerId: str = "") -> WikiListData:
        """列出 wiki 实例（tenantId/ownerId 过滤）。"""
        params: dict[str, str] = {}
        if tenantId:
            params["tenantId"] = tenantId
        if ownerId:
            params["ownerId"] = ownerId
        envelope = self._client.request("GET", "/api/v1/wiki/wikis", params=params)
        return WikiListData.from_dict(envelope.data or {})

    def get(self, wikiId: str) -> WikiMeta:
        """查询 wiki 实例元信息。"""
        envelope = self._client.request("GET", "/api/v1/wiki/wikis/{wiki_id}", path_params={"wiki_id": wikiId})
        return WikiMeta.from_dict(envelope.data or {})

    def delete(self, wikiId: str) -> WikiOpResult:
        """删除 wiki 实例（级联删除页面与文件）。"""
        envelope = self._client.request("DELETE", "/api/v1/wiki/wikis/{wiki_id}", path_params={"wiki_id": wikiId})
        return WikiOpResult.from_dict(envelope.data or {})

    def tree(self, wikiId: str, *, page: int = 1, pageSize: int = 20) -> WikiTreeData:
        """库级页面树（page/pageSize 分页）。"""
        envelope = self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/tree",
            path_params={"wiki_id": wikiId},
            params={"page": page, "pageSize": pageSize},
        )
        return WikiTreeData.from_dict(envelope.data or {})

    def page(self, wikiId: str, pageId: str) -> WikiPageData:
        """单页详情（markdown/fields/links/sourceDocs）。"""
        envelope = self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/page",
            path_params={"wiki_id": wikiId},
            params={"pageId": pageId},
        )
        return WikiPageData.from_dict(envelope.data or {})

    def search(self, wikiId: str, *, q: str = "", tag: str = "", limit: int = 20) -> WikiSearchData:
        """页面检索（q + tag 过滤，评分排序）。"""
        params: dict[str, Any] = {"limit": limit}
        if q:
            params["q"] = q
        if tag:
            params["tag"] = tag
        envelope = self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/search",
            path_params={"wiki_id": wikiId},
            params=params,
        )
        return WikiSearchData.from_dict(envelope.data or {})

    def stat(self, wikiId: str) -> WikiStat:
        """wiki 统计（pageCount/tag 分布/linkCount）。"""
        envelope = self._client.request("GET", "/api/v1/wiki/wikis/{wiki_id}/stat", path_params={"wiki_id": wikiId})
        return WikiStat.from_dict(envelope.data or {})

    def export(self, wikiId: str, *, format: str = "jsonl") -> WikiExport:
        """导出页面（jsonl/json）。"""
        envelope = self._client.request(
            "GET",
            "/api/v1/wiki/wikis/{wiki_id}/export",
            path_params={"wiki_id": wikiId},
            params={"format": format},
        )
        return WikiExport.from_dict(envelope.data or {})

    def build(
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
        """按文档建页；async_=True 时登记为异步任务并返回 WikiJob。"""
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
        envelope = self._client.request("POST", "/api/v1/wiki/wikis/{wiki_id}/build", path_params={"wiki_id": wikiId}, body=body)
        if async_:
            return WikiJob.from_dict(envelope.data or {})
        return BuildResult.from_dict(envelope.data or {})

    def merge(
        self,
        wikiId: str,
        *,
        pages: list[dict[str, Any]] | None = None,
        docId: str = "",
    ) -> BuildResult:
        """显式页面记录增量合并。"""
        body: dict[str, Any] = {"pages": list(pages or [])}
        if docId:
            body["docId"] = docId
        envelope = self._client.request(
            "POST", "/api/v1/wiki/wikis/{wiki_id}/merge", path_params={"wiki_id": wikiId}, body=body
        )
        return BuildResult.from_dict(envelope.data or {})

    def deprecate_doc(self, wikiId: str, *, docId: str) -> WikiOpResult:
        """按 docId 增量废弃页面。"""
        envelope = self._client.request(
            "POST",
            "/api/v1/wiki/wikis/{wiki_id}/deprecate-doc",
            path_params={"wiki_id": wikiId},
            body={"docId": docId},
        )
        return WikiOpResult.from_dict(envelope.data or {})

    def update(self, wikiId: str, *, message: str = "") -> WikiOpResult:
        """OpenWiki 全量刷新（LLM 合成；内核不可用时服务端返回 200001）。"""
        body: dict[str, Any] = {}
        if message:
            body["message"] = message
        envelope = self._client.request(
            "POST", "/api/v1/wiki/wikis/{wiki_id}/update", path_params={"wiki_id": wikiId}, body=body
        )
        return WikiOpResult.from_dict(envelope.data or {})

    def ingest(self, wikiId: str, *, connector: str) -> WikiOpResult:
        """连接器摄取（git-repo/web-search/notion/...；内核不可用时服务端返回 200001）。"""
        envelope = self._client.request(
            "POST",
            "/api/v1/wiki/wikis/{wiki_id}/ingest",
            path_params={"wiki_id": wikiId},
            body={"connector": connector},
        )
        return WikiOpResult.from_dict(envelope.data or {})


class JobsClient:
    """异步任务域客户端：run / get / list。"""

    def __init__(self, client: OpenWikiServerClient) -> None:
        self._client = client

    def run(self, jobId: str) -> WikiJob:
        """同步执行已登记任务（build/merge/deprecate/export/update/ingest）。"""
        envelope = self._client.request(
            "POST", "/api/v1/wiki/jobs/{job_id}/run", path_params={"job_id": jobId}
        )
        return WikiJob.from_dict(envelope.data or {})

    def get(self, jobId: str) -> WikiJob:
        """查询任务状态（pending/active/success/failed）。"""
        envelope = self._client.request("GET", "/api/v1/wiki/jobs/{job_id}", path_params={"job_id": jobId})
        return WikiJob.from_dict(envelope.data or {})

    def list(self, *, wikiId: str = "", limit: int = 20) -> JobListData:
        """列出任务。"""
        params: dict[str, Any] = {"limit": limit}
        if wikiId:
            params["wikiId"] = wikiId
        envelope = self._client.request("GET", "/api/v1/wiki/jobs", params=params)
        return JobListData.from_dict(envelope.data or {})
