"""增量合并规则：对齐 open-ikc WikiPageStore.save 的 merge/overwrite/skip 语义。"""

from __future__ import annotations

from dataclasses import replace

from .models import WikiPageRecord


def _merge_links(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for link in existing + incoming:
        if isinstance(link, dict) and link.get("title"):
            merged[str(link["title"])] = {"title": str(link["title"]), "pageId": str(link.get("pageId") or "")}
    return sorted(merged.values(), key=lambda item: item["title"])


def merge_page(
    existing: WikiPageRecord | None,
    incoming: WikiPageRecord,
    *,
    dedup: str = "merge",
) -> WikiPageRecord:
    """按稳定键合并同名页面。"""
    if existing is None:
        return incoming
    if dedup == "skip":
        return existing
    if dedup == "overwrite":
        return replace(
            incoming,
            page_id=existing.page_id,
            created_at=existing.created_at,
        )
    return replace(
        incoming,
        page_id=existing.page_id,
        created_at=existing.created_at,
        tags=sorted(set(existing.tags) | set(incoming.tags)),
        links=_merge_links(existing.links, incoming.links),
        fields={**dict(existing.fields), **dict(incoming.fields)},
        source_docs=sorted(set(existing.source_docs) | set(incoming.source_docs)),
    )
