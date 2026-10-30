"""增量合并适配：规则来自 ``ikc_sdk.core.wiki_merge``，本地只转换记录类型。"""

from __future__ import annotations

from ikc_sdk.core.wiki_merge import merge_wiki_page_records

from .models import WikiPageRecord


def merge_page(
    existing: WikiPageRecord | None,
    incoming: WikiPageRecord,
    *,
    dedup: str = "merge",
) -> WikiPageRecord:
    """按稳定键合并同名页面。"""
    if existing is None:
        return incoming
    payload = merge_wiki_page_records(
        existing.to_dict(),
        incoming.to_dict(),
        dedup=dedup,
    )
    return WikiPageRecord.from_dict(payload)
