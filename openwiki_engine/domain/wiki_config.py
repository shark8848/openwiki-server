"""wikiConfig 协议适配：校验与默认值来自 ``ikc_sdk.core.wiki_config``。"""

from __future__ import annotations

from typing import Any

from ikc_sdk.core.wiki_config import (
    DEFAULT_WIKI_CONFIG,
    WIKI_DEDUP_MODES,
    WIKI_GRANULARITIES,
    WIKI_LINK_MODES,
    WikiConfigValidationError,
    normalize_wiki_config,
)

from ..errors import InvalidParamsError

# 兼容引擎内部既有命名；取值仍以 SDK 为唯一来源。
GRANULARITIES = WIKI_GRANULARITIES
LINK_MODES = WIKI_LINK_MODES
DEDUP_MODES = WIKI_DEDUP_MODES


def validate_wiki_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """校验并归一化 wikiConfig；缺省字段补默认值，非法即抛 200001。"""
    try:
        return normalize_wiki_config(config)
    except WikiConfigValidationError as exc:
        raise InvalidParamsError(
            "wikiConfig 非法", field=exc.field, reason=exc.reason
        ) from exc
