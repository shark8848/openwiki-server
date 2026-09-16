"""core 数据面回写（引擎 → core 内部写通道）。

契约单一来源：ikc-core-service `docs/API接口与任务契约.md §2.5`
（实现见 core `domain/services/wiki_write_service.py`）：

- `POST {base}/internal/wiki/build`
  `{kbId, docId, pages[], dedup, mode, taskId, engine, engineVersion}`
  → 稳定键 upsert（merge/overwrite/skip）+ `revision_no` 递增与 `wiki_page_version` 快照
    + doc 级增量废弃；回写产物恒 `content_state=draft`（发布走 core `/internal/wiki/review/*`）。
- 鉴权：请求头 `X-Internal-Token` = core `IKC_CORE_ADMIN_TOKEN`。

**分层**：*抽什么*（切页/字段/出链、OKF/LLM 产物）在本引擎；*怎么落地*（合并口径、版本递增、
废弃、审计、审核状态机）在 core，只此一处实现——避免各引擎各写一套（G-05 类跨仓漂移）。

**开关**：未配置 `IKC_CORE_BASE_URL` 时整体关闭（返回 None，无副作用，本地 SQLite 仍是
引擎自带视图的来源）；配置后构建返回体追加 `writeback` 字段。回写失败**不阻断**本地构建
（返回 `{"ok": false, "error": ...}` 并记 warning），便于「引擎可独立运行、按需接入 core」。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def _resolve_version(dist: str) -> str:
    """引擎版本号：repo 内 pyproject 优先（可编辑安装的 dist 元数据常滞后），回落包元数据。"""
    try:
        import tomllib

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.is_file():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            declared = str((data.get("project") or {}).get("version") or "").strip()
            if declared:
                return declared
    except Exception:  # noqa: BLE001 - 任何异常都回落元数据
        pass
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version(dist)
    except Exception:  # noqa: BLE001 - 源码直跑未安装
        return "0.0.0"


ENGINE_VERSION = _resolve_version("openwiki-server")

ENGINE_NAME = "openwiki-server"

# 回落 core 契约字段（extra=forbid）：多余键会被 core 拒绝（100001），此处只投递契约字段
_PAGE_FIELDS = (
    "title",
    "stableKey",
    "level",
    "parentPageId",
    "parentStableKey",
    "unitId",
    "docId",
    "tags",
    "fields",
    "links",
    "sourceDocs",
    "markdown",
    "versionId",
)


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def base_url() -> str:
    return _env("IKC_CORE_BASE_URL").rstrip("/")


def writeback_enabled() -> bool:
    """配置了 core 地址且未显式关闭时启用（默认关闭 = 不改变既有行为）。"""
    if _env("IKC_CORE_WRITEBACK", "1") in ("0", "false", "False", "no", "off"):
        return False
    return bool(base_url())


def page_payload(record: dict[str, Any]) -> dict[str, Any]:
    """引擎页面记录 → core 回写契约字段（去掉 pageId/wikiId/status/时间戳等本地字段）。

    `parentPageId` 直接透传（本引擎已按 `ikc_sdk.core.wiki_ids` 派生同一稳定 ID），
    避免 core 侧按 parentStableKey 二次派生——两者对同一父页必须等价。
    """
    payload = {key: record[key] for key in _PAGE_FIELDS if key in record}
    payload["links"] = [dict(item) for item in (record.get("links") or [])]
    return payload


def _post(path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url()}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Internal-Token": _env("IKC_CORE_ADMIN_TOKEN"),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if str(body.get("errCode")) != "000000":
        raise RuntimeError(f"core 回写失败 {body.get('errCode')}：{body.get('errMsg')}")
    return dict(body.get("data") or {})


def write_pages(
    kb_id: str,
    *,
    doc_id: str = "",
    pages: list[dict[str, Any]] | None = None,
    dedup: str = "",
    mode: str = "openwiki",
    task_id: str = "",
) -> dict[str, Any] | None:
    """把已决策的页面记录回写 core；未启用/无 kbId/空记录 → None（无副作用）。"""
    if not writeback_enabled() or not kb_id or not pages:
        return None
    payload = {
        "kbId": kb_id,
        "docId": doc_id,
        "pages": [page_payload(item) for item in pages],
        "dedup": dedup or "",
        "mode": mode if mode in ("rule", "openwiki") else "openwiki",
        "taskId": task_id,
        "engine": ENGINE_NAME,
        "engineVersion": ENGINE_VERSION,
    }
    timeout = float(_env("IKC_CORE_WRITEBACK_TIMEOUT", "10") or 10)
    try:
        data = _post("/internal/wiki/build", payload, timeout)
    except (urllib.error.URLError, OSError, ValueError, RuntimeError) as exc:
        logger.warning("core 回写未成功（本地构建已完成，数据面未同步）：%s", exc)
        return {"ok": False, "endpoint": "wiki/build", "error": str(exc)}
    return {"ok": True, "endpoint": "wiki/build", **data}


__all__ = [
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "base_url",
    "page_payload",
    "writeback_enabled",
    "write_pages",
]
