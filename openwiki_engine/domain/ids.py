"""稳定 ID 派生规则：与 open-ikc 现有实现保持一致，保证跨侧兼容。"""

from __future__ import annotations

import hashlib
import re


def normalize_title(title: str) -> str:
    """标题规范化：去除空白与标点、统一小写，用于稳定键派生与同名合并。"""
    normalized = re.sub(r"[\W_]+", "", title.strip().lower())
    return normalized or "untitled"


def stable_key_from_filename(filename: str) -> str:
    """从 Markdown 文件名（slug）派生稳定键：去 .md 后按标题规范化。"""
    name = filename.rsplit(".", 1)[0] if filename.endswith(".md") else filename
    return normalize_title(name)


def wiki_id(kb_id: str) -> str:
    """库级 wiki 实例 ID：wiki_ + sha1(kbId) 前 12 位，随库生命周期稳定。"""
    digest = hashlib.sha1(kb_id.encode("utf-8")).hexdigest()
    return f"wiki_{digest[:12]}"


def page_id(kb_id: str, stable_key: str) -> str:
    """稳定页面 ID：wiki_ + sha1(kbId:stableKey) 前 12 位，跨文档/跨构建稳定。"""
    digest = hashlib.sha1(f"{kb_id}:{stable_key}".encode("utf-8")).hexdigest()
    return f"wiki_{digest[:12]}"
