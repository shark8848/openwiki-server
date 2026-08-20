"""应用层：OpenWikiService — HTTP/gRPC/Celery/MCP/CLI 五面共用的用例编排。"""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..adapters.openwiki import (
    _extract_links,
    generate_pages_rule,
    openwiki_available,
    parse_okf_pages,
    run_ingest,
    run_update,
)
from ..config import Settings
from ..domain.ids import normalize_title, page_id, stable_key_from_filename, wiki_id
from ..domain.models import WikiMeta, WikiPageRecord
from ..domain.wiki_config import validate_wiki_config
from ..errors import InvalidParamsError, NotFoundError
from ..persistence.sqlite_store import SqliteWikiStore


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _paginate(records: list[Any], page: int, page_size: int) -> tuple[int, list[Any]]:
    total = len(records)
    start = (page - 1) * page_size
    return total, records[start : start + page_size]


class OpenWikiService:
    """Wiki 引擎应用服务。构造时注入存储；所有用例返回普通 dict（协议层负责序列化）。"""

    def __init__(self, store: SqliteWikiStore, *, settings: Settings | None = None) -> None:
        self.store = store
        self.settings = settings or Settings()

    # ---------- wiki CRUD ----------

    def create_wiki(
        self,
        *,
        wiki_id_value: str = "",
        kb_id: str = "",
        name: str = "",
        tenant_id: str = "",
        owner_id: str = "",
        wiki_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not kb_id:
            raise InvalidParamsError("参数非法", field="kbId", reason="kbId 必填")
        config = validate_wiki_config(wiki_config)
        wid = wiki_id_value.strip() or wiki_id(kb_id)
        now = _now_iso()
        meta = WikiMeta(
            wiki_id=wid,
            kb_id=kb_id,
            name=name,
            tenant_id=tenant_id,
            owner_id=owner_id,
            config=config,
            created_at=now,
            updated_at=now,
        )
        self.store.create_wiki(meta)
        return meta.to_dict()

    def get_wiki(self, wiki_id_value: str) -> dict[str, Any]:
        return self.store.get_wiki_or_raise(wiki_id_value).to_dict()

    def delete_wiki(self, wiki_id_value: str) -> dict[str, Any]:
        self.store.get_wiki_or_raise(wiki_id_value)
        self.store.delete_wiki(wiki_id_value)
        return {"wikiId": wiki_id_value, "deleted": True}

    def list_wikis(self, *, tenant_id: str = "", owner_id: str = "") -> dict[str, Any]:
        metas = self.store.list_wikis(tenant_id=tenant_id, owner_id=owner_id)
        return {"total": len(metas), "items": [meta.to_dict() for meta in metas]}

    def _require_wiki(self, wiki_id_value: str) -> WikiMeta:
        return self.store.get_wiki_or_raise(wiki_id_value)

    # ---------- build / merge / deprecate ----------

    def _record_from_page_dict(self, item: dict[str, Any], meta: WikiMeta, doc_id: str) -> WikiPageRecord:
        record = WikiPageRecord.from_dict(item, wiki_id=meta.wiki_id, kb_id=meta.kb_id)
        if not record.page_id:
            record = replace(record, page_id=page_id(meta.kb_id, record.stable_key))
        effective_doc = record.doc_id or doc_id
        if effective_doc and effective_doc not in record.source_docs:
            record = replace(
                record,
                doc_id=effective_doc,
                source_docs=sorted(set(record.source_docs) | {effective_doc}),
            )
        return record

    def build_from_doc(
        self,
        wiki_id_value: str,
        *,
        doc_id: str = "",
        title: str = "",
        tags: list[str] | None = None,
        markdown: str = "",
        wiki_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """按文档建页：OpenWiki 内核合成（可用时）→ OKF 解析入库；否则规则切页降级。"""
        meta = self._require_wiki(wiki_id_value)
        config = validate_wiki_config({**meta.config, **(wiki_config or {})})
        mode = "rule"
        page_specs: list[dict[str, Any]] = []

        if openwiki_available(self.settings):
            wiki_root = self.store.wiki_root(meta.wiki_id)
            source_dir = Path(wiki_root) / "sources"
            source_path = source_dir / f"{doc_id or uuid.uuid4().hex[:8]}.md"
            source_path.write_text(
                f"# {title or doc_id}\n\n{markdown}",
                encoding="utf-8",
            )
            message = (
                f"根据文档 {doc_id or source_path.name}（标题：{title or '未命名'}）"
                f"生成 wiki 页面，遵守 wikiConfig：{json.dumps(config, ensure_ascii=False)}。"
            )
            update = run_update(
                wiki_root,
                provider=self.settings.openwiki_provider,
                model_id=self.settings.openwiki_model_id,
                message=message,
                timeout=self.settings.openwiki_update_timeout,
                settings=self.settings,
            )
            if update.get("ok"):
                parsed = parse_okf_pages(
                    self.store.openwiki_wiki_dir(meta.wiki_id), kb_id=meta.kb_id
                )
                if parsed:
                    mode = "openwiki"
                    for item in parsed:
                        page_specs.append(
                            {
                                "title": item["title"],
                                "stableKey": item["stableKey"],
                                "tags": item["tags"],
                                "fields": item["fields"],
                                "markdown": item["markdown"],
                                "links": item["links"],
                                "sourceDocs": item["sourceDocs"] or [doc_id],
                                "status": item["status"],
                            }
                        )

        if not page_specs:
            for item in generate_pages_rule(
                markdown,
                title=title or doc_id or "未命名文档",
                tags=tags,
                config=config,
            ):
                page_specs.append(
                    {
                        **item,
                        "sourceDocs": [doc_id] if doc_id else [],
                        "links": _extract_links(item["markdown"], meta.kb_id)
                        if config.get("linkMode") == "auto"
                        else [],
                    }
                )

        saved: list[WikiPageRecord] = []
        for item in page_specs:
            item["stableKey"] = normalize_title(str(item.get("stableKey") or item.get("title") or "untitled"))
            record = WikiPageRecord.from_dict(item, wiki_id=meta.wiki_id, kb_id=meta.kb_id)
            record = replace(
                record,
                page_id=page_id(meta.kb_id, record.stable_key),
                doc_id=doc_id,
                source_docs=sorted(set(record.source_docs) | ({doc_id} if doc_id else set())),
                level=int(item.get("level") or 1),
                parent_page_id=(
                    page_id(meta.kb_id, normalize_title(str(item.get("parentStableKey") or "")))
                    if item.get("parentStableKey")
                    else ""
                ),
                status=str(item.get("status") or "active"),
            )
            saved.append(self.store.upsert_page(record, dedup=config.get("dedup") or "merge"))

        deprecated = 0
        if doc_id:
            active_keys = {record.stable_key for record in saved}
            deprecated = self.store.deprecate_doc_pages(meta.kb_id, doc_id, active_keys)

        return {
            "wikiId": meta.wiki_id,
            "kbId": meta.kb_id,
            "docId": doc_id,
            "mode": mode,
            "total": len(saved),
            "deprecated": deprecated,
            "pages": [record.to_dict() for record in saved],
        }

    def merge_records(
        self,
        wiki_id_value: str,
        *,
        pages: list[dict[str, Any]] | None = None,
        doc_id: str = "",
    ) -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        config = validate_wiki_config(meta.config)
        saved: list[WikiPageRecord] = []
        for item in pages or []:
            record = self._record_from_page_dict(item, meta, doc_id)
            if not record.page_id:
                raise InvalidParamsError(
                    "页面缺少稳定键", field="pages", reason="pageId 或 title/stableKey 必填"
                )
            saved.append(self.store.upsert_page(record, dedup=config.get("dedup") or "merge"))
        return {
            "wikiId": meta.wiki_id,
            "kbId": meta.kb_id,
            "docId": doc_id,
            "total": len(saved),
            "pages": [record.to_dict() for record in saved],
        }

    def deprecate_doc(self, wiki_id_value: str, *, doc_id: str = "") -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        if not doc_id:
            raise InvalidParamsError("参数非法", field="docId", reason="docId 必填")
        deprecated = self.store.deprecate_doc_pages(meta.kb_id, doc_id, set())
        return {"wikiId": meta.wiki_id, "kbId": meta.kb_id, "docId": doc_id, "deprecated": deprecated}

    # ---------- 查询 ----------

    def tree(self, wiki_id_value: str, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        roots = self.store.build_tree(meta.kb_id)
        total, tree_slice = _paginate(roots, page, page_size)
        return {
            "wikiId": meta.wiki_id,
            "kbId": meta.kb_id,
            "kbMode": "wiki",
            "total": total,
            "page": page,
            "pageSize": page_size,
            "tree": tree_slice,
        }

    def page(self, wiki_id_value: str, *, page_id_value: str) -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        record = self.store.get_page(page_id_value)
        if record is None or record.wiki_id != meta.wiki_id:
            raise NotFoundError("Wiki 页面不存在", field="pageId", reason=f"pageId：{page_id_value}")
        return {"wikiId": meta.wiki_id, "kbId": meta.kb_id, "kbMode": "wiki", "page": record.to_dict()}

    def search(
        self,
        wiki_id_value: str,
        *,
        q: str = "",
        tag: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        hits = self.store.search(meta.kb_id, q, tag.strip() or None, limit=limit)
        items = [
            {
                "pageId": record.page_id,
                "title": record.title,
                "snippet": self._snippet(record.markdown),
                "tags": list(record.tags),
                "score": score,
            }
            for record, score in hits
        ]
        return {
            "wikiId": meta.wiki_id,
            "kbId": meta.kb_id,
            "kbMode": "wiki",
            "q": q,
            "total": len(items),
            "items": items,
        }

    @staticmethod
    def _snippet(markdown: str, length: int = 80) -> str:
        import re

        first_line = markdown.strip().splitlines()[0] if markdown.strip() else ""
        plain = re.sub(r"[#*`>\[\]()]+", "", first_line).strip()
        return plain[:length]

    def stat(self, wiki_id_value: str) -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        stat = self.store.stat(meta.wiki_id)
        stat["wikiId"] = meta.wiki_id
        stat["kbId"] = meta.kb_id
        return stat

    def export(self, wiki_id_value: str, *, format: str = "jsonl") -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        lines = self.store.export_lines(meta.wiki_id)
        fmt = (format or "jsonl").strip().lower()
        if fmt == "jsonl":
            return {
                "wikiId": meta.wiki_id,
                "kbId": meta.kb_id,
                "format": "jsonl",
                "total": len(lines),
                "content": "\n".join(lines),
            }
        if fmt == "json":
            records = [json.loads(line) for line in lines]
            return {
                "wikiId": meta.wiki_id,
                "kbId": meta.kb_id,
                "format": "json",
                "total": len(records),
                "content": json.dumps({"pages": records}, ensure_ascii=False),
            }
        raise InvalidParamsError("导出格式暂不支持", field="format", reason=f"支持 jsonl/json，当前：{fmt}")

    # ---------- OpenWiki 内核增强 ----------

    def update_wiki(self, wiki_id_value: str, *, message: str = "") -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        if not openwiki_available(self.settings):
            raise InvalidParamsError(
                "OpenWiki 内核不可用",
                field="openwiki",
                reason="openwiki 未安装或 OPENWIKI_SERVER_OPENWIKI=0",
            )
        result = run_update(
            self.store.wiki_root(meta.wiki_id),
            provider=self.settings.openwiki_provider,
            model_id=self.settings.openwiki_model_id,
            message=message,
            timeout=self.settings.openwiki_update_timeout,
            settings=self.settings,
        )
        return {"wikiId": meta.wiki_id, "kbId": meta.kb_id, "result": result}

    def ingest(self, wiki_id_value: str, *, connector: str = "") -> dict[str, Any]:
        meta = self._require_wiki(wiki_id_value)
        if not connector:
            raise InvalidParamsError("参数非法", field="connector", reason="connector 必填")
        if not openwiki_available(self.settings):
            raise InvalidParamsError(
                "OpenWiki 内核不可用",
                field="openwiki",
                reason="openwiki 未安装或 OPENWIKI_SERVER_OPENWIKI=0",
            )
        result = run_ingest(
            self.store.wiki_root(meta.wiki_id),
            connector,
            settings=self.settings,
        )
        return {"wikiId": meta.wiki_id, "kbId": meta.kb_id, "connector": connector, "result": result}

    # ---------- jobs（异步任务登记与执行） ----------

    def submit_job(
        self, task: str, wiki_id_value: str = "", payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self.store.create_job(job_id, wiki_id_value, task, dict(payload or {}))
        return {"jobId": job_id, "wikiId": wiki_id_value, "task": task, "status": "pending"}

    def run_job(self, job_id: str) -> dict[str, Any]:
        """同步执行已登记任务（Celery worker 与 HTTP async 复用）。"""
        job = self.store.get_job(job_id)
        if job is None:
            raise NotFoundError("任务不存在", field="jobId", reason=job_id)
        if job["status"] in ("success", "failed"):
            return job
        task = job["task"]
        payload = dict(job["payload"] or {})
        wiki_id_value = str(job.get("wikiId") or "")
        try:
            if task == "build":
                result = self.build_from_doc(
                    wiki_id_value,
                    doc_id=str(payload.get("docId") or ""),
                    title=str(payload.get("title") or ""),
                    tags=payload.get("tags") or [],
                    markdown=str(payload.get("markdown") or ""),
                    wiki_config=payload.get("wikiConfig"),
                )
            elif task == "merge":
                result = self.merge_records(
                    wiki_id_value, pages=payload.get("pages") or [], doc_id=str(payload.get("docId") or "")
                )
            elif task == "deprecate_doc":
                result = self.deprecate_doc(wiki_id_value, doc_id=str(payload.get("docId") or ""))
            elif task == "export":
                result = self.export(wiki_id_value, format=str(payload.get("format") or "jsonl"))
            elif task == "update":
                result = self.update_wiki(wiki_id_value, message=str(payload.get("message") or ""))
            elif task == "ingest":
                result = self.ingest(wiki_id_value, connector=str(payload.get("connector") or ""))
            else:
                raise InvalidParamsError("未知任务", field="task", reason=task)
            self.store.update_job(job_id, status="success", result=result)
        except Exception as exc:
            self.store.update_job(job_id, status="failed", error=str(exc))
            raise
        return self.store.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job is None:
            raise NotFoundError("任务不存在", field="jobId", reason=job_id)
        return job

    def list_jobs(self, *, wiki_id_value: str = "", limit: int = 20) -> dict[str, Any]:
        jobs = self.store.list_jobs(wiki_id=wiki_id_value, limit=limit)
        return {"total": len(jobs), "items": jobs}
