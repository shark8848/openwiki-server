"""Pure Celery task bodies shared by the native worker and the IKC registrar.

This module must not create or import a Celery app. The native worker decorates
these functions in ``openwiki_engine.interfaces.celery_app``; the registrar
imports them directly and registers them on its own app.
"""

from __future__ import annotations

from typing import Any, Callable

from ..runtime import get_service


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


def build(
    wiki_id: str,
    doc_id: str = "",
    title: str = "",
    tags: list[str] | None = None,
    markdown: str = "",
    wiki_config: dict[str, Any] | None = None,
    job_id: str = "",
) -> dict[str, Any]:
    """按文档建页任务。"""
    svc = get_service()
    return _run_job(
        job_id,
        lambda: svc.build_from_doc(
            wiki_id,
            doc_id=doc_id,
            title=title,
            tags=tags or [],
            markdown=markdown,
            wiki_config=wiki_config,
        ),
    )


def merge(
    wiki_id: str,
    pages: list[dict[str, Any]] | None = None,
    doc_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """增量合并任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.merge_records(wiki_id, pages=pages or [], doc_id=doc_id))


def deprecate_doc(wiki_id: str, doc_id: str, job_id: str = "") -> dict[str, Any]:
    """按 docId 增量废弃任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.deprecate_doc(wiki_id, doc_id=doc_id))


def export(wiki_id: str, format: str = "jsonl", job_id: str = "") -> dict[str, Any]:
    """导出任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.export(wiki_id, format=format))


def update(wiki_id: str, message: str = "", job_id: str = "") -> dict[str, Any]:
    """OpenWiki 全量刷新任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.update_wiki(wiki_id, message=message))


def ingest(wiki_id: str, connector: str, job_id: str = "") -> dict[str, Any]:
    """连接器摄取任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.ingest(wiki_id, connector=connector))
