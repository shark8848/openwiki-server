from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _extra(data: dict[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in known}


@dataclass
class WikiMeta:
    """Wiki 实例元信息（对应 POST/GET /api/v1/wiki/wikis）。"""

    wikiId: str
    kbId: str = ""
    name: str = ""
    tenantId: str = ""
    ownerId: str = ""
    wikiConfig: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    createdAt: str = ""
    updatedAt: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiMeta":
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            name=str(data.get("name", "")),
            tenantId=str(data.get("tenantId", "")),
            ownerId=str(data.get("ownerId", "")),
            wikiConfig=dict(data.get("wikiConfig") or {}),
            status=str(data.get("status", "active")),
            createdAt=str(data.get("createdAt", "")),
            updatedAt=str(data.get("updatedAt", "")),
            extra=_extra(data, {"wikiId", "kbId", "name", "tenantId", "ownerId", "wikiConfig", "status", "createdAt", "updatedAt"}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "name": self.name,
            "tenantId": self.tenantId,
            "ownerId": self.ownerId,
            "wikiConfig": dict(self.wikiConfig),
            "status": self.status,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            **self.extra,
        }


@dataclass
class WikiListData:
    """Wiki 实例列表（GET /api/v1/wiki/wikis）。"""

    total: int = 0
    items: list[WikiMeta] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiListData":
        return cls(
            total=int(data.get("total") or 0),
            items=[WikiMeta.from_dict(item) for item in (data.get("items") or []) if isinstance(item, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "items": [item.to_dict() for item in self.items]}


@dataclass
class WikiTreeNode:
    """Wiki 页面树节点（对应 GET /api/v1/wiki/wikis/{id}/tree）。"""

    pageId: str
    title: str
    level: int
    parentPageId: str = ""
    children: list["WikiTreeNode"] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiTreeNode":
        return cls(
            pageId=str(data.get("pageId", "")),
            title=str(data.get("title", "")),
            level=int(data.get("level") or 1),
            parentPageId=str(data.get("parentPageId", "")),
            children=[WikiTreeNode.from_dict(item) for item in (data.get("children") or []) if isinstance(item, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageId": self.pageId,
            "title": self.title,
            "level": self.level,
            "parentPageId": self.parentPageId,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class WikiTreeData:
    """Wiki 页面树查询结果。"""

    wikiId: str = ""
    kbId: str = ""
    kbMode: str = "wiki"
    total: int = 0
    page: int = 1
    pageSize: int = 20
    tree: list[WikiTreeNode] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiTreeData":
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            kbMode=str(data.get("kbMode", "wiki")),
            total=int(data.get("total") or 0),
            page=int(data.get("page") or 1),
            pageSize=int(data.get("pageSize") or 20),
            tree=[WikiTreeNode.from_dict(item) for item in (data.get("tree") or []) if isinstance(item, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "kbMode": self.kbMode,
            "total": self.total,
            "page": self.page,
            "pageSize": self.pageSize,
            "tree": [node.to_dict() for node in self.tree],
        }


@dataclass
class WikiPageDetail:
    """Wiki 页面详情（对应 GET /api/v1/wiki/wikis/{id}/page 的 data.page）。"""

    pageId: str = ""
    wikiId: str = ""
    kbId: str = ""
    docId: str = ""
    title: str = ""
    level: int = 1
    parentPageId: str = ""
    stableKey: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    markdown: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    sourceDocs: list[str] = field(default_factory=list)
    status: str = "active"
    createdAt: str = ""
    updatedAt: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiPageDetail":
        return cls(
            pageId=str(data.get("pageId", "")),
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            docId=str(data.get("docId", "")),
            title=str(data.get("title", "")),
            level=int(data.get("level") or 1),
            parentPageId=str(data.get("parentPageId", "")),
            stableKey=str(data.get("stableKey", "")),
            fields=dict(data.get("fields") or {}),
            tags=[str(tag) for tag in (data.get("tags") or [])],
            markdown=str(data.get("markdown", "")),
            links=[dict(link) for link in (data.get("links") or []) if isinstance(link, dict)],
            sourceDocs=[str(doc) for doc in (data.get("sourceDocs") or [])],
            status=str(data.get("status", "active")),
            createdAt=str(data.get("createdAt", "")),
            updatedAt=str(data.get("updatedAt", "")),
            extra=_extra(
                data,
                {"pageId", "wikiId", "kbId", "docId", "title", "level", "parentPageId", "stableKey",
                 "fields", "tags", "markdown", "links", "sourceDocs", "status", "createdAt", "updatedAt"},
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageId": self.pageId,
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "docId": self.docId,
            "title": self.title,
            "level": self.level,
            "parentPageId": self.parentPageId,
            "stableKey": self.stableKey,
            "fields": dict(self.fields),
            "tags": list(self.tags),
            "markdown": self.markdown,
            "links": [dict(link) for link in self.links],
            "sourceDocs": list(self.sourceDocs),
            "status": self.status,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            **self.extra,
        }


@dataclass
class WikiPageData:
    """Wiki 页面详情查询结果（GET .../page）。"""

    wikiId: str = ""
    kbId: str = ""
    kbMode: str = "wiki"
    page: WikiPageDetail | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiPageData":
        page_data = data.get("page")
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            kbMode=str(data.get("kbMode", "wiki")),
            page=WikiPageDetail.from_dict(page_data) if isinstance(page_data, dict) else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "kbMode": self.kbMode,
            "page": self.page.to_dict() if self.page is not None else None,
        }


@dataclass
class WikiSearchHit:
    """Wiki 检索命中条目（对应 GET .../search 的 data.items）。"""

    pageId: str
    title: str
    snippet: str = ""
    tags: list[str] = field(default_factory=list)
    score: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiSearchHit":
        score = data.get("score")
        return cls(
            pageId=str(data.get("pageId", "")),
            title=str(data.get("title", "")),
            snippet=str(data.get("snippet", "")),
            tags=[str(tag) for tag in (data.get("tags") or [])],
            score=float(score) if score is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageId": self.pageId,
            "title": self.title,
            "snippet": self.snippet,
            "tags": list(self.tags),
            "score": self.score,
        }


@dataclass
class WikiSearchData:
    """Wiki 页面检索结果。"""

    wikiId: str = ""
    kbId: str = ""
    kbMode: str = "wiki"
    q: str = ""
    total: int = 0
    items: list[WikiSearchHit] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiSearchData":
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            kbMode=str(data.get("kbMode", "wiki")),
            q=str(data.get("q", "")),
            total=int(data.get("total") or 0),
            items=[WikiSearchHit.from_dict(item) for item in (data.get("items") or []) if isinstance(item, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "kbMode": self.kbMode,
            "q": self.q,
            "total": self.total,
            "items": [hit.to_dict() for hit in self.items],
        }


@dataclass
class WikiStat:
    """Wiki 统计（GET .../stat）。"""

    wikiId: str = ""
    kbId: str = ""
    pageCount: int = 0
    active: int = 0
    deprecated: int = 0
    linkCount: int = 0
    tags: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiStat":
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            pageCount=int(data.get("pageCount") or 0),
            active=int(data.get("active") or 0),
            deprecated=int(data.get("deprecated") or 0),
            linkCount=int(data.get("linkCount") or 0),
            tags={str(key): int(value) for key, value in (data.get("tags") or {}).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "pageCount": self.pageCount,
            "active": self.active,
            "deprecated": self.deprecated,
            "linkCount": self.linkCount,
            "tags": dict(self.tags),
        }


@dataclass
class WikiExport:
    """Wiki 导出（GET .../export）。"""

    wikiId: str = ""
    kbId: str = ""
    format: str = "jsonl"
    total: int = 0
    content: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiExport":
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            format=str(data.get("format", "jsonl")),
            total=int(data.get("total") or 0),
            content=str(data.get("content", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "format": self.format,
            "total": self.total,
            "content": self.content,
        }


@dataclass
class BuildResult:
    """按文档建页 / 增量合并结果（POST .../build、.../merge）。"""

    wikiId: str = ""
    kbId: str = ""
    docId: str = ""
    mode: str = "rule"
    total: int = 0
    deprecated: int = 0
    pages: list[WikiPageDetail] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuildResult":
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            docId=str(data.get("docId", "")),
            mode=str(data.get("mode", "rule")),
            total=int(data.get("total") or 0),
            deprecated=int(data.get("deprecated") or 0),
            pages=[WikiPageDetail.from_dict(item) for item in (data.get("pages") or []) if isinstance(item, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wikiId,
            "kbId": self.kbId,
            "docId": self.docId,
            "mode": self.mode,
            "total": self.total,
            "deprecated": self.deprecated,
            "pages": [page.to_dict() for page in self.pages],
        }


@dataclass
class WikiJob:
    """异步任务（POST/GET /api/v1/wiki/jobs*）。"""

    jobId: str = ""
    wikiId: str = ""
    task: str = ""
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str = ""
    createdAt: str = ""
    updatedAt: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiJob":
        return cls(
            jobId=str(data.get("jobId", "")),
            wikiId=str(data.get("wikiId", "")),
            task=str(data.get("task", "")),
            status=str(data.get("status", "pending")),
            payload=dict(data.get("payload") or {}),
            result=data.get("result"),
            error=str(data.get("error", "")),
            createdAt=str(data.get("createdAt", "")),
            updatedAt=str(data.get("updatedAt", "")),
            extra=_extra(data, {"jobId", "wikiId", "task", "status", "payload", "result", "error", "createdAt", "updatedAt"}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "jobId": self.jobId,
            "wikiId": self.wikiId,
            "task": self.task,
            "status": self.status,
            "payload": dict(self.payload),
            "result": self.result,
            "error": self.error,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            **self.extra,
        }


@dataclass
class JobListData:
    """异步任务列表（GET /api/v1/wiki/jobs）。"""

    total: int = 0
    items: list[WikiJob] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobListData":
        return cls(
            total=int(data.get("total") or 0),
            items=[WikiJob.from_dict(item) for item in (data.get("items") or []) if isinstance(item, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "items": [job.to_dict() for job in self.items]}


@dataclass
class WikiOpResult:
    """通用操作结果（delete / deprecate-doc / update / ingest）。"""

    wikiId: str = ""
    kbId: str = ""
    docId: str = ""
    deleted: bool | None = None
    deprecated: int | None = None
    connector: str = ""
    result: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiOpResult":
        deleted = data.get("deleted")
        deprecated = data.get("deprecated")
        return cls(
            wikiId=str(data.get("wikiId", "")),
            kbId=str(data.get("kbId", "")),
            docId=str(data.get("docId", "")),
            deleted=bool(deleted) if deleted is not None else None,
            deprecated=int(deprecated) if deprecated is not None else None,
            connector=str(data.get("connector", "")),
            result=data.get("result"),
            extra=_extra(data, {"wikiId", "kbId", "docId", "deleted", "deprecated", "connector", "result"}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"wikiId": self.wikiId, "kbId": self.kbId, "docId": self.docId}
        if self.deleted is not None:
            payload["deleted"] = self.deleted
        if self.deprecated is not None:
            payload["deprecated"] = self.deprecated
        if self.connector:
            payload["connector"] = self.connector
        if self.result is not None:
            payload["result"] = self.result
        payload.update(self.extra)
        return payload
