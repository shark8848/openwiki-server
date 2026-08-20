"""Celery 协议面：异步任务（build / merge / deprecate / export / update / ingest）。

任务与 HTTP async 模式共用 application 层；broker/backend 由环境变量配置，
默认 redis://localhost:6379/0。
"""

from __future__ import annotations

from typing import Any

from celery import Celery

from ..config import Settings
from ..runtime import get_service

_settings = Settings()

celery_app = Celery(
    "openwiki_server",
    broker=_settings.celery_broker,
    backend=_settings.celery_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)


def _finish_job(job_id: str, result: dict[str, Any]) -> None:
    """任务完成后回写引擎 job 表（HTTP async 可轮询）。"""
    if job_id:
        get_service().store.update_job(job_id, status="success", result=result)


@celery_app.task(name="openwiki_server.build")
def build_task(
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
    result = svc.build_from_doc(
        wiki_id,
        doc_id=doc_id,
        title=title,
        tags=tags or [],
        markdown=markdown,
        wiki_config=wiki_config,
    )
    _finish_job(job_id, result)
    return result


@celery_app.task(name="openwiki_server.merge")
def merge_task(
    wiki_id: str,
    pages: list[dict[str, Any]] | None = None,
    doc_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """增量合并任务。"""
    svc = get_service()
    result = svc.merge_records(wiki_id, pages=pages or [], doc_id=doc_id)
    _finish_job(job_id, result)
    return result


@celery_app.task(name="openwiki_server.deprecate_doc")
def deprecate_doc_task(wiki_id: str, doc_id: str, job_id: str = "") -> dict[str, Any]:
    """按 docId 增量废弃任务。"""
    svc = get_service()
    result = svc.deprecate_doc(wiki_id, doc_id=doc_id)
    _finish_job(job_id, result)
    return result


@celery_app.task(name="openwiki_server.export")
def export_task(wiki_id: str, format: str = "jsonl", job_id: str = "") -> dict[str, Any]:
    """导出任务。"""
    svc = get_service()
    result = svc.export(wiki_id, format=format)
    _finish_job(job_id, result)
    return result


@celery_app.task(name="openwiki_server.update")
def update_task(wiki_id: str, message: str = "", job_id: str = "") -> dict[str, Any]:
    """OpenWiki 全量刷新任务。"""
    svc = get_service()
    result = svc.update_wiki(wiki_id, message=message)
    _finish_job(job_id, result)
    return result


@celery_app.task(name="openwiki_server.ingest")
def ingest_task(wiki_id: str, connector: str, job_id: str = "") -> dict[str, Any]:
    """连接器摄取任务。"""
    svc = get_service()
    result = svc.ingest(wiki_id, connector=connector)
    _finish_job(job_id, result)
    return result


def worker_main(argv: list[str] | None = None) -> None:
    """启动 worker（供 `openwiki-server serve worker` 调用）。"""
    celery_app.worker_main(argv or ["worker", "-l", "info"])
