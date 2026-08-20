"""领域层：稳定 ID / 页面模型 / wikiConfig 校验 / 合并规则。"""

from .ids import normalize_title, page_id, stable_key_from_filename, wiki_id
from .merge import merge_page
from .models import WikiMeta, WikiPageRecord
from .wiki_config import DEFAULT_WIKI_CONFIG, validate_wiki_config

__all__ = [
    "DEFAULT_WIKI_CONFIG",
    "WikiMeta",
    "WikiPageRecord",
    "merge_page",
    "normalize_title",
    "page_id",
    "stable_key_from_filename",
    "validate_wiki_config",
    "wiki_id",
]
