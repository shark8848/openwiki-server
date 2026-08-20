from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class WikiMeta:
    wiki_id: str
    kb_id: str = ""
    name: str = ""
    tenant_id: str = ""
    owner_id: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wikiId": self.wiki_id,
            "kbId": self.kb_id,
            "name": self.name,
            "tenantId": self.tenant_id,
            "ownerId": self.owner_id,
            "wikiConfig": dict(self.config),
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WikiMeta":
        return cls(
            wiki_id=str(data.get("wikiId") or data.get("wiki_id") or ""),
            kb_id=str(data.get("kbId") or ""),
            name=str(data.get("name") or ""),
            tenant_id=str(data.get("tenantId") or ""),
            owner_id=str(data.get("ownerId") or ""),
            config=dict(data.get("wikiConfig") or {}),
            status=str(data.get("status") or "active"),
            created_at=str(data.get("createdAt") or _now_iso()),
            updated_at=str(data.get("updatedAt") or _now_iso()),
        )


@dataclass(frozen=True, slots=True)
class WikiPageRecord:
    page_id: str
    wiki_id: str
    kb_id: str
    doc_id: str
    title: str
    level: int
    parent_page_id: str
    stable_key: str
    fields: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    markdown: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    source_docs: list[str] = field(default_factory=list)
    status: str = "active"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageId": self.page_id,
            "wikiId": self.wiki_id,
            "kbId": self.kb_id,
            "docId": self.doc_id,
            "title": self.title,
            "level": self.level,
            "parentPageId": self.parent_page_id,
            "stableKey": self.stable_key,
            "fields": dict(self.fields),
            "tags": list(self.tags),
            "markdown": self.markdown,
            "links": [dict(item) for item in self.links],
            "sourceDocs": list(self.source_docs),
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, wiki_id: str = "", kb_id: str = "") -> "WikiPageRecord":
        from .ids import normalize_title, page_id

        wid = str(data.get("wikiId") or wiki_id or "")
        kid = str(data.get("kbId") or kb_id or "")
        title = str(data.get("title") or "未命名页面")
        stable_key = str(data.get("stableKey") or normalize_title(title))
        return cls(
            page_id=str(data.get("pageId") or (page_id(kid, stable_key) if kid else "")),
            wiki_id=wid,
            kb_id=kid,
            doc_id=str(data.get("docId") or ""),
            title=title,
            level=int(data.get("level") or 1),
            parent_page_id=str(data.get("parentPageId") or ""),
            stable_key=stable_key,
            fields=dict(data.get("fields") or {}),
            tags=[str(x) for x in (data.get("tags") or [])],
            markdown=str(data.get("markdown") or ""),
            links=[dict(x) for x in (data.get("links") or []) if isinstance(x, dict)],
            source_docs=[str(x) for x in (data.get("sourceDocs") or [])],
            status=str(data.get("status") or "active"),
            created_at=str(data.get("createdAt") or _now_iso()),
            updated_at=str(data.get("updatedAt") or _now_iso()),
        )
