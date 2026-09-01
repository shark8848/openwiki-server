"""HTTP 协议面：FastAPI，前缀 /api/v1/wiki，响应 envelope 与 open-ikc 对齐。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from ..config import Settings
from ..errors import OpenWikiError
from ..logging_setup import configure_logging
from ..protocol import TRACE_ID_HEADER, error, new_trace_id, ok
from ..runtime import get_service


def _trace(request: Request) -> str:
    return request.headers.get(TRACE_ID_HEADER) or new_trace_id()


def _handle(trace_id: str, fn) -> JSONResponse:
    try:
        return JSONResponse(ok(trace_id, fn()))
    except OpenWikiError as exc:
        status = (
            400
            if exc.code == "200001"
            else 404
            if exc.code == "200404"
            else 409
            if exc.code == "200409"
            else 500
        )
        return JSONResponse(error(trace_id, exc), status_code=status)
    except Exception as exc:  # pragma: no cover
        return JSONResponse(error(trace_id, exc), status_code=500)


def create_app(service: Any | None = None) -> FastAPI:
    settings = Settings()
    configure_logging(level=settings.log_level, log_center=settings.log_center)
    svc = service or get_service()
    app = FastAPI(title="OpenWiki Server", version="0.3.2")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "openwiki-server"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        return {"status": "ready"}

    # ---------- wiki CRUD ----------

    @app.post("/api/v1/wiki/wikis")
    def create_wiki(request: Request, payload: dict[str, Any]) -> JSONResponse:
        tid = _trace(request)
        return _handle(
            tid,
            lambda: svc.create_wiki(
                wiki_id_value=str(payload.get("wikiId") or ""),
                kb_id=str(payload.get("kbId") or ""),
                name=str(payload.get("name") or ""),
                tenant_id=str(payload.get("tenantId") or ""),
                owner_id=str(payload.get("ownerId") or ""),
                wiki_config=payload.get("wikiConfig"),
            ),
        )

    @app.get("/api/v1/wiki/wikis")
    def list_wikis(
        request: Request,
        tenantId: str = Query(default=""),
        ownerId: str = Query(default=""),
    ) -> JSONResponse:
        tid = _trace(request)
        return _handle(
            tid, lambda: svc.list_wikis(tenant_id=tenantId, owner_id=ownerId)
        )

    @app.get("/api/v1/wiki/wikis/{wiki_id}")
    def get_wiki(request: Request, wiki_id: str) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.get_wiki(wiki_id))

    @app.delete("/api/v1/wiki/wikis/{wiki_id}")
    def delete_wiki(request: Request, wiki_id: str) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.delete_wiki(wiki_id))

    # ---------- 查询 ----------

    @app.get("/api/v1/wiki/wikis/{wiki_id}/tree")
    def wiki_tree(
        request: Request,
        wiki_id: str,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=20, ge=1, le=100),
    ) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.tree(wiki_id, page=page, page_size=pageSize))

    @app.get("/api/v1/wiki/wikis/{wiki_id}/page")
    def wiki_page(request: Request, wiki_id: str, pageId: str = Query(...)) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.page(wiki_id, page_id_value=pageId))

    @app.get("/api/v1/wiki/wikis/{wiki_id}/search")
    def wiki_search(
        request: Request,
        wiki_id: str,
        q: str = Query(default=""),
        tag: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.search(wiki_id, q=q, tag=tag, limit=limit))

    @app.get("/api/v1/wiki/wikis/{wiki_id}/stat")
    def wiki_stat(request: Request, wiki_id: str) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.stat(wiki_id))

    @app.get("/api/v1/wiki/wikis/{wiki_id}/export")
    def wiki_export(
        request: Request, wiki_id: str, format: str = Query(default="jsonl")
    ) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.export(wiki_id, format=format))

    # ---------- 加工 ----------

    @app.post("/api/v1/wiki/wikis/{wiki_id}/build")
    def build_wiki(request: Request, wiki_id: str, payload: dict[str, Any]) -> JSONResponse:
        tid = _trace(request)
        if str(payload.get("async") or "").lower() in ("1", "true", "yes"):
            return _handle(
                tid,
                lambda: svc.submit_job("build", wiki_id, payload),
            )
        return _handle(
            tid,
            lambda: svc.build_from_doc(
                wiki_id,
                doc_id=str(payload.get("docId") or ""),
                title=str(payload.get("title") or ""),
                tags=payload.get("tags") or [],
                markdown=str(payload.get("markdown") or ""),
                wiki_config=payload.get("wikiConfig"),
            ),
        )

    @app.post("/api/v1/wiki/wikis/{wiki_id}/merge")
    def merge_wiki(request: Request, wiki_id: str, payload: dict[str, Any]) -> JSONResponse:
        tid = _trace(request)
        return _handle(
            tid,
            lambda: svc.merge_records(
                wiki_id,
                pages=payload.get("pages") or [],
                doc_id=str(payload.get("docId") or ""),
            ),
        )

    @app.post("/api/v1/wiki/wikis/{wiki_id}/deprecate-doc")
    def deprecate_doc(request: Request, wiki_id: str, payload: dict[str, Any]) -> JSONResponse:
        tid = _trace(request)
        return _handle(
            tid, lambda: svc.deprecate_doc(wiki_id, doc_id=str(payload.get("docId") or ""))
        )

    @app.post("/api/v1/wiki/wikis/{wiki_id}/update")
    def update_wiki(request: Request, wiki_id: str, payload: dict[str, Any]) -> JSONResponse:
        tid = _trace(request)
        return _handle(
            tid, lambda: svc.update_wiki(wiki_id, message=str(payload.get("message") or ""))
        )

    @app.post("/api/v1/wiki/wikis/{wiki_id}/ingest")
    def ingest_wiki(request: Request, wiki_id: str, payload: dict[str, Any]) -> JSONResponse:
        tid = _trace(request)
        return _handle(
            tid, lambda: svc.ingest(wiki_id, connector=str(payload.get("connector") or ""))
        )

    # ---------- jobs ----------

    @app.post("/api/v1/wiki/jobs/{job_id}/run")
    def run_job(request: Request, job_id: str) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.run_job(job_id))

    @app.get("/api/v1/wiki/jobs/{job_id}")
    def get_job(request: Request, job_id: str) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.get_job(job_id))

    @app.get("/api/v1/wiki/jobs")
    def list_jobs(
        request: Request,
        wikiId: str = Query(default=""),
        limit: int = Query(default=20),
    ) -> JSONResponse:
        tid = _trace(request)
        return _handle(tid, lambda: svc.list_jobs(wiki_id_value=wikiId, limit=limit))

    return app
