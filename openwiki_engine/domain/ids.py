"""稳定 ID 派生：直接复用 ``ikc_sdk.core.wiki_ids`` 的跨仓单一来源。"""

from __future__ import annotations

from ikc_sdk.core.wiki_ids import (
    normalize_title,
    page_id_for,
    stable_key_from_filename,
    wiki_id_for,
)

# 兼容引擎既有调用名；算法本身只在 ikc-sdk-lib 维护。
wiki_id = wiki_id_for
page_id = page_id_for

__all__ = [
    "normalize_title",
    "page_id",
    "stable_key_from_filename",
    "wiki_id",
]
