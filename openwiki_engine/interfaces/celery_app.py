"""Celery 协议面：异步任务（build / merge / deprecate / export / update / ingest）。

任务与 HTTP async 模式共用 application 层；连接形态（单机 / 副本 / 哨兵）由
OPENWIKI_SERVER_CELERY_* 环境变量经 ikc_sdk.celery 解析，默认 redis://localhost:6379/0。
"""

from __future__ import annotations

from typing import Any

from ikc_sdk.celery import CeleryFactory
from ikc_sdk.core.queues import (
    TASK_OPENWIKI_BUILD,
    TASK_OPENWIKI_DEPRECATE_DOC,
    TASK_OPENWIKI_EXPORT,
    TASK_OPENWIKI_INGEST,
    TASK_OPENWIKI_MERGE,
    TASK_OPENWIKI_UPDATE,
)

from ..celery_tasks import handlers
from ..config import Settings

_settings = Settings()

# 单机 / 副本形态以 Settings 派生 URL 为准（工厂的入参口径）；哨兵形态由
# OPENWIKI_SERVER_CELERY_SENTINEL_* 生成，入参与 OPENWIKI_SERVER_CELERY_BROKER* 都不参与。
celery_app = CeleryFactory.create(
    "openwiki_server",
    prefix="OPENWIKI_SERVER_CELERY",
    broker_url=_settings.celery_broker,
    result_backend=_settings.celery_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    task_default_queue=_settings.celery_queue,
)


@celery_app.task(name=TASK_OPENWIKI_BUILD)
def build_task(
    wiki_id: str,
    doc_id: str = "",
    title: str = "",
    tags: list[str] | None = None,
    markdown: str = "",
    markdown_file_id: str = "",
    wiki_config: dict[str, Any] | None = None,
    job_id: str = "",
) -> dict[str, Any]:
    """按文档建页任务。"""
    return handlers.build(
        wiki_id=wiki_id,
        doc_id=doc_id,
        title=title,
        tags=tags,
        markdown=markdown,
        markdown_file_id=markdown_file_id,
        wiki_config=wiki_config,
        job_id=job_id,
    )


@celery_app.task(name=TASK_OPENWIKI_MERGE)
def merge_task(
    wiki_id: str,
    pages: list[dict[str, Any]] | None = None,
    doc_id: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    """增量合并任务。"""
    return handlers.merge(
        wiki_id=wiki_id, pages=pages, doc_id=doc_id, job_id=job_id
    )


@celery_app.task(name=TASK_OPENWIKI_DEPRECATE_DOC)
def deprecate_doc_task(wiki_id: str, doc_id: str, job_id: str = "") -> dict[str, Any]:
    """按 docId 增量废弃任务。"""
    return handlers.deprecate_doc(wiki_id=wiki_id, doc_id=doc_id, job_id=job_id)


@celery_app.task(name=TASK_OPENWIKI_EXPORT)
def export_task(wiki_id: str, format: str = "jsonl", job_id: str = "") -> dict[str, Any]:
    """导出任务。"""
    return handlers.export(wiki_id=wiki_id, format=format, job_id=job_id)


@celery_app.task(name=TASK_OPENWIKI_UPDATE)
def update_task(wiki_id: str, message: str = "", job_id: str = "") -> dict[str, Any]:
    """OpenWiki 全量刷新任务。"""
    return handlers.update(wiki_id=wiki_id, message=message, job_id=job_id)


@celery_app.task(name=TASK_OPENWIKI_INGEST)
def ingest_task(wiki_id: str, connector: str, job_id: str = "") -> dict[str, Any]:
    """连接器摄取任务。"""
    return handlers.ingest(wiki_id=wiki_id, connector=connector, job_id=job_id)


def worker_main(argv: list[str] | None = None) -> None:
    """启动 worker（供 `openwiki-server serve worker` 调用）。"""
    from ..logging_setup import configure_logging

    configure_logging(level=_settings.log_level, log_center=_settings.log_center)
    celery_app.worker_main(argv or ["worker", "-l", "info"])


# prefork 子进程丢失投递线程：注册 worker_process_init 重建钩子（幂等，失败不阻断）
from ..logging_setup import attach_celery_fork_hook

attach_celery_fork_hook(celery_app)
