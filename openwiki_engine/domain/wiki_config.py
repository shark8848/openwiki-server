"""wikiConfig 校验与默认值：与 open-ikc Wiki 库配置语义保持一致。"""

from __future__ import annotations

from typing import Any

from ..errors import InvalidParamsError

DEFAULT_WIKI_CONFIG: dict[str, Any] = {
    "granularity": "auto",
    "extractFields": [],
    "linkMode": "auto",
    "dedup": "merge",
    "template": "",
}

GRANULARITIES = ("auto", "heading", "section", "page")
LINK_MODES = ("auto", "off")
DEDUP_MODES = ("merge", "overwrite", "skip")


def validate_wiki_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """校验并归一化 wikiConfig；缺省字段补默认值，非法即抛 200001。"""
    config = dict(config or {})
    normalized: dict[str, Any] = dict(DEFAULT_WIKI_CONFIG)
    normalized.update(config)

    granularity = str(normalized.get("granularity") or "auto").strip().lower()
    if granularity not in GRANULARITIES:
        raise InvalidParamsError(
            "wikiConfig 非法",
            field="wikiConfig.granularity",
            reason=f"granularity 必须为 {'/'.join(GRANULARITIES)}，当前：{granularity}",
        )
    normalized["granularity"] = granularity

    extract_fields = normalized.get("extractFields") or []
    if not isinstance(extract_fields, list) or not all(isinstance(x, str) for x in extract_fields):
        raise InvalidParamsError(
            "wikiConfig 非法",
            field="wikiConfig.extractFields",
            reason="extractFields 必须为字符串数组",
        )
    normalized["extractFields"] = list(extract_fields)

    link_mode = str(normalized.get("linkMode") or "auto").strip().lower()
    if link_mode not in LINK_MODES:
        raise InvalidParamsError(
            "wikiConfig 非法",
            field="wikiConfig.linkMode",
            reason=f"linkMode 必须为 {'/'.join(LINK_MODES)}，当前：{link_mode}",
        )
    normalized["linkMode"] = link_mode

    dedup = str(normalized.get("dedup") or "merge").strip().lower()
    if dedup not in DEDUP_MODES:
        raise InvalidParamsError(
            "wikiConfig 非法",
            field="wikiConfig.dedup",
            reason=f"dedup 必须为 {'/'.join(DEDUP_MODES)}，当前：{dedup}",
        )
    normalized["dedup"] = dedup

    if not isinstance(normalized.get("template", ""), str):
        raise InvalidParamsError(
            "wikiConfig 非法", field="wikiConfig.template", reason="template 必须为字符串"
        )
    return normalized
