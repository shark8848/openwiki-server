"""CLI 协议面：typer 命令 openwiki-server，与 open-ikc `ikc` CLI 风格一致。"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional

import typer

from ..application.service import OpenWikiService
from ..errors import OpenWikiError
from ..runtime import get_service

app = typer.Typer(
    name="openwiki-server",
    help="OpenWiki Server 命令行（HTTP/gRPC/Celery/MCP/CLI 五面接口）",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

_service: OpenWikiService | None = None
_global_json = False


def _svc() -> OpenWikiService:
    if _service is None:
        return get_service()
    return _service


def _emit(data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, default=str)
    typer.echo(text)


def _exit_for(err: BaseException) -> None:
    if isinstance(err, OpenWikiError):
        raise typer.Exit(str(err.message), code=1)
    raise typer.Exit(str(err), code=6)


@app.callback()
def _main(
    db_path: Optional[str] = typer.Option(None, "--db-path", help="SQLite 存储路径（覆盖环境变量）"),
    json_output: bool = typer.Option(False, "--json", help="输出原始 JSON"),
) -> None:
    global _service, _global_json
    from ..runtime import get_store, get_settings

    _global_json = json_output
    if db_path:
        settings = get_settings()
        _service = OpenWikiService(get_store(db_path), settings=settings)


# ---------- serve ----------


@app.command()
def serve(
    kind: str = typer.Argument(..., help="http | grpc | mcp | worker"),
    host: str = typer.Option("", help="监听地址（默认取配置）"),
    port: int = typer.Option(0, help="监听端口（默认取配置）"),
) -> None:
    """启动协议面服务。"""
    from ..config import Settings

    settings = Settings()
    if kind == "http":
        import uvicorn

        uvicorn.run(
            "openwiki_engine.interfaces.http_app:create_app",
            host=host or settings.http_host,
            port=port or settings.http_port,
            factory=True,
        )
    elif kind == "grpc":
        from .grpc_server import serve_grpc

        serve_grpc(host=host or settings.grpc_host, port=port or settings.grpc_port)
    elif kind == "mcp":
        from .mcp_server import serve_mcp

        serve_mcp()
    elif kind == "worker":
        from .celery_app import worker_main

        worker_main(argv=["worker", "-l", "info"])
    else:
        raise typer.BadParameter(f"未知服务类型：{kind}（支持 http|grpc|mcp|worker）")


# ---------- wiki ----------


@app.command()
def create(
    kb_id: str = typer.Option(..., "--kb-id", help="open-ikc 知识库 ID（wikiId 派生自 kbId）"),
    name: str = typer.Option("", "--name"),
    wiki_id: str = typer.Option("", "--wiki-id"),
    tenant_id: str = typer.Option("", "--tenant-id"),
    owner_id: str = typer.Option("", "--owner-id"),
    config_json: str = typer.Option("", "--config", help="wikiConfig JSON 字符串"),
) -> None:
    """创建 wiki 实例。"""
    try:
        config = json.loads(config_json) if config_json else {}
        _emit(
            _svc().create_wiki(
                wiki_id_value=wiki_id,
                kb_id=kb_id,
                name=name,
                tenant_id=tenant_id,
                owner_id=owner_id,
                wiki_config=config,
            )
        )
    except Exception as exc:
        _exit_for(exc)


@app.command("list")
def list_wikis(
    tenant_id: str = typer.Option("", "--tenant-id"),
    owner_id: str = typer.Option("", "--owner-id"),
) -> None:
    """列出 wiki 实例。"""
    try:
        _emit(_svc().list_wikis(tenant_id=tenant_id, owner_id=owner_id))
    except Exception as exc:
        _exit_for(exc)


@app.command("get")
def get_wiki(wiki_id: str = typer.Argument(...)) -> None:
    """查询 wiki 实例元信息。"""
    try:
        _emit(_svc().get_wiki(wiki_id))
    except Exception as exc:
        _exit_for(exc)


@app.command("delete")
def delete_wiki(wiki_id: str = typer.Argument(...)) -> None:
    """删除 wiki 实例。"""
    try:
        _emit(_svc().delete_wiki(wiki_id))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def tree(
    wiki_id: str = typer.Argument(...),
    page: int = typer.Option(1, "--page"),
    page_size: int = typer.Option(20, "--page-size"),
) -> None:
    """查询页面树。"""
    try:
        _emit(_svc().tree(wiki_id, page=page, page_size=page_size))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def page(
    wiki_id: str = typer.Argument(...),
    page_id: str = typer.Option(..., "--page-id"),
) -> None:
    """查询页面详情。"""
    try:
        _emit(_svc().page(wiki_id, page_id_value=page_id))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def search(
    wiki_id: str = typer.Argument(...),
    q: str = typer.Option("", "--q"),
    tag: str = typer.Option("", "--tag"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """检索页面。"""
    try:
        _emit(_svc().search(wiki_id, q=q, tag=tag, limit=limit))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def stat(wiki_id: str = typer.Argument(...)) -> None:
    """wiki 统计。"""
    try:
        _emit(_svc().stat(wiki_id))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def build(
    wiki_id: str = typer.Argument(...),
    doc_id: str = typer.Option("", "--doc-id"),
    title: str = typer.Option("", "--title"),
    tags: str = typer.Option("", "--tags", help="逗号分隔的标签"),
    markdown: str = typer.Option("", "--markdown"),
    config_json: str = typer.Option("", "--config", help="任务级 wikiConfig JSON"),
) -> None:
    """按文档建页。"""
    try:
        _emit(
            _svc().build_from_doc(
                wiki_id,
                doc_id=doc_id,
                title=title,
                tags=[x.strip() for x in tags.split(",") if x.strip()] if tags else [],
                markdown=markdown,
                wiki_config=json.loads(config_json) if config_json else None,
            )
        )
    except Exception as exc:
        _exit_for(exc)


@app.command()
def merge(
    wiki_id: str = typer.Argument(...),
    pages_json: str = typer.Option(..., "--pages", help='[{"title":..., "markdown":...}] JSON'),
    doc_id: str = typer.Option("", "--doc-id"),
) -> None:
    """增量合并页面记录。"""
    try:
        _emit(_svc().merge_records(wiki_id, pages=json.loads(pages_json), doc_id=doc_id))
    except Exception as exc:
        _exit_for(exc)


@app.command("deprecate-doc")
def deprecate_doc(wiki_id: str = typer.Argument(...), doc_id: str = typer.Argument(...)) -> None:
    """按 docId 增量废弃。"""
    try:
        _emit(_svc().deprecate_doc(wiki_id, doc_id=doc_id))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def export(wiki_id: str = typer.Argument(...), format: str = typer.Option("jsonl", "--format")) -> None:
    """导出页面（jsonl/json）。"""
    try:
        _emit(_svc().export(wiki_id, format=format))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def update(
    wiki_id: str = typer.Argument(...),
    message: str = typer.Option("", "--message"),
) -> None:
    """OpenWiki 全量刷新（LLM 合成）。"""
    try:
        _emit(_svc().update_wiki(wiki_id, message=message))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def ingest(wiki_id: str = typer.Argument(...), connector: str = typer.Argument(...)) -> None:
    """连接器摄取（git-repo/web-search/notion/...）。"""
    try:
        _emit(_svc().ingest(wiki_id, connector=connector))
    except Exception as exc:
        _exit_for(exc)


# ---------- job ----------


@app.command()
def job_run(job_id: str = typer.Argument(...)) -> None:
    """同步执行任务。"""
    try:
        _emit(_svc().run_job(job_id))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def job_get(job_id: str = typer.Argument(...)) -> None:
    """查询任务状态。"""
    try:
        _emit(_svc().get_job(job_id))
    except Exception as exc:
        _exit_for(exc)


@app.command()
def job_list(
    wiki_id: str = typer.Option("", "--wiki-id"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """列出任务。"""
    try:
        _emit(_svc().list_jobs(wiki_id_value=wiki_id, limit=limit))
    except Exception as exc:
        _exit_for(exc)
