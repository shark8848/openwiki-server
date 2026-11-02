"""Pure Celery task bodies shared by the native worker and the IKC registrar.

This module must not create or import a Celery app. The native worker decorates
these functions in ``openwiki_engine.interfaces.celery_app``; the registrar
imports them directly and registers them on its own app.

TM dispatches ``args=(payload_json,)`` while the native worker passes flat
``kwargs``. Both forms are accepted here. A TM envelope also carries the task
links needed for best-effort ``begin`` / ``end`` reporting; reporting failures
never change the business result.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from celery import current_app

from ..runtime import get_service

logger = logging.getLogger("openwiki_engine.tm")

# Wire constants stay local so the registrar task package can import without
# requiring a newer optional ikc-sdk-lib just for queue names.
TASK_OPENWIKI_BUILD = "openwiki_server.build"
TASK_OPENWIKI_MERGE = "openwiki_server.merge"
TASK_OPENWIKI_DEPRECATE_DOC = "openwiki_server.deprecate_doc"
TASK_OPENWIKI_EXPORT = "openwiki_server.export"
TASK_OPENWIKI_UPDATE = "openwiki_server.update"
TASK_OPENWIKI_INGEST = "openwiki_server.ingest"

TM_TASK_UPDATER = "ikc_tm_task_updater"
TM_QUEUE_UPDATER = "ikc_tm_task_updater"
TM_STATUS_SUCCEEDED = "SUCCEEDED"
TM_STATUS_FAILED = "FAILED"

# TM 纳管任务 → 接入点名（apiName）。TM 配置与这里必须保持同名映射。
TM_API_BY_TASK: dict[str, str] = {
    TASK_OPENWIKI_BUILD: "ikc_tm_wiki_build",
    TASK_OPENWIKI_MERGE: "ikc_tm_wiki_merge",
    TASK_OPENWIKI_DEPRECATE_DOC: "ikc_tm_wiki_deprecate_doc",
    TASK_OPENWIKI_EXPORT: "ikc_tm_wiki_export",
    TASK_OPENWIKI_UPDATE: "ikc_tm_wiki_update",
    TASK_OPENWIKI_INGEST: "ikc_tm_wiki_ingest",
}

_TM_PROTOCOL_FIELDS = frozenset(
    {"taskId", "reqId", "traceId", "taskStrategy", "apiName", "category"}
)


def _text(data: Mapping[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _as_mapping(
    payload: Any, kwargs: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Accept flat native kwargs and TM's JSON envelope."""
    value = dict(kwargs) if payload is None else payload
    if isinstance(value, (str, bytes, bytearray)):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise TypeError("wiki task payload must be a JSON object")

    envelope = dict(value)
    body = envelope.get("body")
    wrapped = isinstance(body, Mapping)
    business = dict(body) if wrapped else envelope
    links = {"task_id": "", "req_id": "", "trace_id": ""}
    if wrapped:
        links = {
            "task_id": str(
                envelope.get("task_id")
                or envelope.get("taskId")
                or business.get("taskId")
                or ""
            ).strip(),
            "req_id": str(
                envelope.get("req_id") or business.get("reqId") or ""
            ).strip(),
            "trace_id": str(
                envelope.get("trace_id") or business.get("traceId") or ""
            ).strip(),
        }
        for key in _TM_PROTOCOL_FIELDS:
            business.pop(key, None)
    return business, links


def _headers(links: Mapping[str, str]) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    if links.get("trace_id"):
        headers["X-Request-Id"] = links["trace_id"]
    if links.get("req_id"):
        headers["X-Req-Id"] = links["req_id"]
    return headers or None


def _report(
    op: str,
    *,
    task: str,
    links: Mapping[str, str],
    succeeded: bool = True,
    message: str = "",
) -> None:
    task_id = str(links.get("task_id") or "")
    api_name = TM_API_BY_TASK.get(task)
    if not task_id or not api_name:
        return
    body: dict[str, Any] = {
        "op": op,
        "taskId": task_id,
        "stage": task,
        "taskApiName": api_name,
        "status": TM_STATUS_SUCCEEDED if succeeded else TM_STATUS_FAILED,
    }
    if links.get("req_id"):
        body["reqId"] = links["req_id"]
    if links.get("trace_id"):
        body["traceId"] = links["trace_id"]
    if message:
        body["message"] = message
    try:
        current_app.send_task(
            TM_TASK_UPDATER,
            args=({"apiName": TM_TASK_UPDATER, "body": body},),
            queue=TM_QUEUE_UPDATER,
            headers=_headers(links),
        )
    except Exception as exc:  # noqa: BLE001 - lifecycle reporting is a side channel
        logger.warning(
            "TM 生命周期上报失败 op=%s task=%s taskId=%s: %s",
            op,
            task,
            task_id,
            exc,
        )


def _run_reported(
    task_name: str,
    runner: Callable[[dict[str, Any]], dict[str, Any]],
    payload: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    business, links = _as_mapping(payload, kwargs)
    if links.get("task_id"):
        _report("begin", task=task_name, links=links)
    try:
        result = runner(business)
    except Exception as exc:
        if links.get("task_id"):
            _report(
                "end",
                task=task_name,
                links=links,
                succeeded=False,
                message=f"{type(exc).__name__}: {exc}",
            )
        raise
    if links.get("task_id"):
        _report("end", task=task_name, links=links)
    return result


def _run_job(job_id: str, run: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """执行任务体并把终态回写引擎 job 表。"""
    try:
        result = run()
    except Exception as exc:
        if job_id:
            get_service().store.update_job(job_id, status="failed", error=str(exc))
        raise
    if job_id:
        get_service().store.update_job(job_id, status="success", result=result)
    return result


def _build(data: dict[str, Any]) -> dict[str, Any]:
    svc = get_service()
    wiki_id = _text(data, "wiki_id", "wikiId")
    kb_id = _text(data, "kb_id", "kbId")
    if kb_id:
        svc.ensure_wiki(wiki_id, kb_id=kb_id)
    return _run_job(
        _text(data, "job_id", "jobId"),
        lambda: svc.build_from_doc(
            wiki_id,
            doc_id=_text(data, "doc_id", "docId"),
            title=_text(data, "title"),
            tags=data.get("tags") or [],
            markdown=_text(data, "markdown"),
            markdown_file_id=_text(data, "markdown_file_id", "markdownFileId"),
            wiki_config=data.get("wiki_config") or data.get("wikiConfig") or {},
            model_id=_text(data, "model_id", "modelId"),
        ),
    )


def build(payload: Any = None, **kwargs: Any) -> dict[str, Any]:
    """按文档建页任务。"""
    return _run_reported(TASK_OPENWIKI_BUILD, _build, payload, **kwargs)


def _merge(data: dict[str, Any]) -> dict[str, Any]:
    svc = get_service()
    return _run_job(
        _text(data, "job_id", "jobId"),
        lambda: svc.merge_records(
            _text(data, "wiki_id", "wikiId"),
            pages=data.get("pages") or [],
            doc_id=_text(data, "doc_id", "docId"),
        ),
    )


def merge(payload: Any = None, **kwargs: Any) -> dict[str, Any]:
    """增量合并任务。"""
    return _run_reported(TASK_OPENWIKI_MERGE, _merge, payload, **kwargs)


def _deprecate_doc(data: dict[str, Any]) -> dict[str, Any]:
    svc = get_service()
    return _run_job(
        _text(data, "job_id", "jobId"),
        lambda: svc.deprecate_doc(
            _text(data, "wiki_id", "wikiId"),
            doc_id=_text(data, "doc_id", "docId"),
        ),
    )


def deprecate_doc(payload: Any = None, **kwargs: Any) -> dict[str, Any]:
    """按 docId 增量废弃任务。"""
    return _run_reported(
        TASK_OPENWIKI_DEPRECATE_DOC, _deprecate_doc, payload, **kwargs
    )


def _export(data: dict[str, Any]) -> dict[str, Any]:
    svc = get_service()
    return _run_job(
        _text(data, "job_id", "jobId"),
        lambda: svc.export(
            _text(data, "wiki_id", "wikiId"),
            format=_text(data, "format", default="jsonl"),
        ),
    )


def export(payload: Any = None, **kwargs: Any) -> dict[str, Any]:
    """导出任务。"""
    return _run_reported(TASK_OPENWIKI_EXPORT, _export, payload, **kwargs)


def _update(data: dict[str, Any]) -> dict[str, Any]:
    svc = get_service()
    return _run_job(
        _text(data, "job_id", "jobId"),
        lambda: svc.update_wiki(
            _text(data, "wiki_id", "wikiId"),
            message=_text(data, "message"),
        ),
    )


def update(payload: Any = None, **kwargs: Any) -> dict[str, Any]:
    """OpenWiki 全量刷新任务。"""
    return _run_reported(TASK_OPENWIKI_UPDATE, _update, payload, **kwargs)


def _ingest(data: dict[str, Any]) -> dict[str, Any]:
    svc = get_service()
    return _run_job(
        _text(data, "job_id", "jobId"),
        lambda: svc.ingest(
            _text(data, "wiki_id", "wikiId"),
            connector=_text(data, "connector"),
        ),
    )


def ingest(payload: Any = None, **kwargs: Any) -> dict[str, Any]:
    """连接器摄取任务。"""
    return _run_reported(TASK_OPENWIKI_INGEST, _ingest, payload, **kwargs)
