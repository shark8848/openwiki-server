"""Celery 协议面：异步任务（build / merge / deprecate / export / update / ingest）。

任务与 HTTP async 模式共用 application 层；broker/backend 由环境变量配置，
默认 redis://localhost:6379/0。
"""

from __future__ import annotations

from typing import Any, Callable

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


def _run_job(job_id: str, run: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """执行任务体并把**终态**回写引擎 job 表（HTTP async / W-07 轮询据此判定）。

    异常必须落 `failed` + `error`：引擎只在成功时回写 job 的话，任务抛异常（如目标资源不存在）
    会让作业永远停在 `pending`，调用方只能靠轮询超时猜失败。异常照旧向上抛，Celery 保持
    标准的 FAILURE 语义。
    """
    try:
        result = run()
    except Exception as exc:
        if job_id:
            get_service().store.update_job(job_id, status="failed", error=str(exc))
        raise
    if job_id:
        get_service().store.update_job(job_id, status="success", result=result)
    return result


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


@celery_app.task(name="openwiki_server.merge")
def merge_task(
    wiki_id: str,
    pages: list[dict[str, Any]] | None = None,
    doc_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """增量合并任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.merge_records(wiki_id, pages=pages or [], doc_id=doc_id))


@celery_app.task(name="openwiki_server.deprecate_doc")
def deprecate_doc_task(wiki_id: str, doc_id: str, job_id: str = "") -> dict[str, Any]:
    """按 docId 增量废弃任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.deprecate_doc(wiki_id, doc_id=doc_id))


@celery_app.task(name="openwiki_server.export")
def export_task(wiki_id: str, format: str = "jsonl", job_id: str = "") -> dict[str, Any]:
    """导出任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.export(wiki_id, format=format))


@celery_app.task(name="openwiki_server.update")
def update_task(wiki_id: str, message: str = "", job_id: str = "") -> dict[str, Any]:
    """OpenWiki 全量刷新任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.update_wiki(wiki_id, message=message))


@celery_app.task(name="openwiki_server.ingest")
def ingest_task(wiki_id: str, connector: str, job_id: str = "") -> dict[str, Any]:
    """连接器摄取任务。"""
    svc = get_service()
    return _run_job(job_id, lambda: svc.ingest(wiki_id, connector=connector))


def worker_main(argv: list[str] | None = None) -> None:
    """启动 worker（供 `openwiki-server serve worker` 调用）。"""
    from ..logging_setup import configure_logging

    configure_logging(level=_settings.log_level, log_center=_settings.log_center)
    celery_app.worker_main(argv or ["worker", "-l", "info"])
