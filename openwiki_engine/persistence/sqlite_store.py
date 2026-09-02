"""SQLite 主存储：wikis / pages / jobs 三表，WAL + 线程安全。

页面以稳定 ID（wiki_ + sha1(kbId:stableKey)）为主键，fields/tags/links/sourceDocs
以 JSON 列存储，保持与 open-ikc 现有 WikiPageRecord DTO 一致。
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..domain.ids import normalize_title
from ..domain.merge import merge_page
from ..domain.models import WikiMeta, WikiPageRecord
from ..errors import ConflictError, NotFoundError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS wikis (
  wiki_id     TEXT PRIMARY KEY,
  kb_id       TEXT NOT NULL DEFAULT '',
  name        TEXT NOT NULL DEFAULT '',
  tenant_id   TEXT NOT NULL DEFAULT '',
  owner_id    TEXT NOT NULL DEFAULT '',
  config_json TEXT NOT NULL DEFAULT '{}',
  status      TEXT NOT NULL DEFAULT 'active',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
  page_id         TEXT PRIMARY KEY,
  wiki_id         TEXT NOT NULL DEFAULT '',
  kb_id           TEXT NOT NULL DEFAULT '',
  doc_id          TEXT NOT NULL DEFAULT '',
  title           TEXT NOT NULL DEFAULT '',
  level           INTEGER NOT NULL DEFAULT 1,
  parent_page_id  TEXT NOT NULL DEFAULT '',
  stable_key      TEXT NOT NULL DEFAULT '',
  fields_json     TEXT NOT NULL DEFAULT '{}',
  tags_json       TEXT NOT NULL DEFAULT '[]',
  markdown        TEXT NOT NULL DEFAULT '',
  links_json      TEXT NOT NULL DEFAULT '[]',
  source_docs_json TEXT NOT NULL DEFAULT '[]',
  status          TEXT NOT NULL DEFAULT 'active',
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_wiki ON pages(wiki_id, status);
CREATE INDEX IF NOT EXISTS idx_pages_key ON pages(kb_id, stable_key, status);
CREATE TABLE IF NOT EXISTS jobs (
  job_id       TEXT PRIMARY KEY,
  wiki_id      TEXT NOT NULL DEFAULT '',
  task         TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',
  payload_json TEXT NOT NULL DEFAULT '{}',
  result_json  TEXT,
  error        TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);
"""


class SqliteWikiStore:
    """SQLite Wiki 存储实现。进程内单连接 + 互斥锁，保证读写原子性。"""

    def __init__(self, db_path: str, *, data_dir: str = "data") -> None:
        self.db_path = db_path
        self.data_dir = data_dir
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.commit()

    # ---------- wiki 文件根目录 ----------

    def wiki_root(self, wiki_id: str) -> str:
        root = Path(self.data_dir).expanduser().resolve() / "wikis" / wiki_id
        root.mkdir(parents=True, exist_ok=True)
        (root / ".openwiki" / "wiki").mkdir(parents=True, exist_ok=True)
        (root / "sources").mkdir(parents=True, exist_ok=True)
        return str(root)

    def openwiki_wiki_dir(self, wiki_id: str) -> str:
        return str(Path(self.wiki_root(wiki_id)) / ".openwiki" / "wiki")

    # ---------- wikis ----------

    def create_wiki(self, meta: WikiMeta) -> WikiMeta:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM wikis WHERE wiki_id=?", (meta.wiki_id,)).fetchone()
            if row:
                raise ConflictError(
                    "Wiki 实例已存在", field="wikiId", reason=f"wikiId 冲突：{meta.wiki_id}"
                )
            self.wiki_root(meta.wiki_id)
            self._conn.execute(
                "INSERT INTO wikis(wiki_id, kb_id, name, tenant_id, owner_id, config_json, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    meta.wiki_id,
                    meta.kb_id,
                    meta.name,
                    meta.tenant_id,
                    meta.owner_id,
                    json.dumps(meta.config, ensure_ascii=False),
                    meta.status,
                    meta.created_at,
                    meta.updated_at,
                ),
            )
            self._conn.commit()
            return meta

    def get_wiki(self, wiki_id: str) -> WikiMeta | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM wikis WHERE wiki_id=?", (wiki_id,)).fetchone()
        return self._row_to_wiki(row) if row else None

    def get_wiki_or_raise(self, wiki_id: str) -> WikiMeta:
        meta = self.get_wiki(wiki_id)
        if meta is None:
            raise NotFoundError("Wiki 实例不存在", field="wikiId", reason=f"wikiId：{wiki_id}")
        return meta

    def list_wikis(self, *, tenant_id: str = "", owner_id: str = "") -> list[WikiMeta]:
        sql = "SELECT * FROM wikis"
        conds: list[str] = []
        params: list[str] = []
        if tenant_id:
            conds.append("tenant_id=?")
            params.append(tenant_id)
        if owner_id:
            conds.append("owner_id=?")
            params.append(owner_id)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_wiki(row) for row in rows]

    def delete_wiki(self, wiki_id: str) -> None:
        with self._lock:
            self.get_wiki_or_raise(wiki_id)
            self._conn.execute("DELETE FROM wikis WHERE wiki_id=?", (wiki_id,))
            self._conn.execute("DELETE FROM pages WHERE wiki_id=?", (wiki_id,))
            self._conn.execute("DELETE FROM jobs WHERE wiki_id=?", (wiki_id,))
            self._conn.commit()
        shutil.rmtree(Path(self.data_dir) / "wikis" / wiki_id, ignore_errors=True)

    # ---------- pages ----------

    def upsert_page(self, record: WikiPageRecord, *, dedup: str = "merge") -> WikiPageRecord:
        with self._lock:
            existing = self._find_by_key_locked(record.kb_id, record.stable_key)
            if existing is not None:
                record = merge_page(existing, record, dedup=dedup)
            self._conn.execute(
                "INSERT INTO pages(page_id, wiki_id, kb_id, doc_id, title, level, parent_page_id,"
                " stable_key, fields_json, tags_json, markdown, links_json, source_docs_json,"
                " status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(page_id) DO UPDATE SET"
                " wiki_id=excluded.wiki_id, kb_id=excluded.kb_id, doc_id=excluded.doc_id,"
                " title=excluded.title, level=excluded.level, parent_page_id=excluded.parent_page_id,"
                " stable_key=excluded.stable_key, fields_json=excluded.fields_json,"
                " tags_json=excluded.tags_json, markdown=excluded.markdown, links_json=excluded.links_json,"
                " source_docs_json=excluded.source_docs_json, status=excluded.status,"
                " created_at=excluded.created_at, updated_at=excluded.updated_at",
                (
                    record.page_id,
                    record.wiki_id,
                    record.kb_id,
                    record.doc_id,
                    record.title,
                    record.level,
                    record.parent_page_id,
                    record.stable_key,
                    json.dumps(record.fields, ensure_ascii=False),
                    json.dumps(record.tags, ensure_ascii=False),
                    record.markdown,
                    json.dumps(record.links, ensure_ascii=False),
                    json.dumps(record.source_docs, ensure_ascii=False),
                    record.status,
                    record.created_at,
                    record.updated_at,
                ),
            )
            self._conn.commit()
            return record

    def get_page(self, page_id: str) -> WikiPageRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM pages WHERE page_id=?", (page_id,)).fetchone()
        return self._row_to_page(row) if row else None

    def list_pages(self, wiki_id: str, *, status: str = "active") -> list[WikiPageRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM pages WHERE wiki_id=? AND status=? ORDER BY title",
                (wiki_id, status),
            ).fetchall()
        return [self._row_to_page(row) for row in rows]

    def _find_by_key_locked(self, kb_id: str, stable_key: str) -> WikiPageRecord | None:
        row = self._conn.execute(
            "SELECT * FROM pages WHERE kb_id=? AND stable_key=? AND status='active'",
            (kb_id, stable_key),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_page(row)

    def deprecate_doc_pages(self, kb_id: str, doc_id: str, active_stable_keys: set[str]) -> int:
        """增量废弃：仅由该文档贡献、且本次构建未再出现的活跃页面标记 deprecated。"""
        deprecated = 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM pages WHERE kb_id=? AND status='active'", (kb_id,)
            ).fetchall()
            for row in rows:
                record = self._row_to_page(row)
                if doc_id not in record.source_docs:
                    continue
                if record.stable_key in active_stable_keys:
                    continue
                if set(record.source_docs) != {doc_id}:
                    continue
                self._conn.execute(
                    "UPDATE pages SET status='deprecated', updated_at=? WHERE page_id=?",
                    (_now_iso(), record.page_id),
                )
                deprecated += 1
            self._conn.commit()
        return deprecated

    # ---------- 树 / 检索 / 统计 ----------

    def build_tree(self, kb_id: str) -> list[dict[str, Any]]:
        """构建库级页面树：按 parentPageId 挂接子页面，无父页面者为根节点。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM pages WHERE kb_id=? AND status='active'", (kb_id,)
            ).fetchall()
        records = [self._row_to_page(row) for row in rows]
        nodes: dict[str, dict[str, Any]] = {}
        for record in records:
            nodes[record.page_id] = {
                "pageId": record.page_id,
                "title": record.title,
                "level": record.level,
                "parentPageId": record.parent_page_id,
                "children": [],
            }
        roots: list[dict[str, Any]] = []
        for record in records:
            node = nodes[record.page_id]
            parent = nodes.get(record.parent_page_id)
            if parent is not None and parent is not node:
                parent["children"].append(node)
            else:
                roots.append(node)
        return roots

    def search(
        self,
        kb_id: str,
        q: str,
        tag: str | None = None,
        *,
        limit: int = 20,
    ) -> list[tuple[WikiPageRecord, float]]:
        """库内页面检索：标题命中加权 > 正文命中；可附加 tag 过滤。q 为空时返回全部页面。"""
        q_raw = (q or "").strip()
        q_norm = normalize_title(q_raw)
        hits: list[tuple[WikiPageRecord, float]] = []
        for record in self.list_pages_by_kb(kb_id):
            if tag and tag not in record.tags:
                continue
            title_norm = normalize_title(record.title)
            content_norm = normalize_title(re.sub(r"[\s#*`>\-\n]+", "", record.markdown))
            if q_raw:
                score = 0.0
                if q_norm in title_norm:
                    score += 10.0
                if q_norm in content_norm:
                    score += 3.0
                for link in record.links:
                    if q_norm in normalize_title(link.get("title", "")):
                        score += 1.0
                if score <= 0:
                    continue
            else:
                score = 1.0
            hits.append((record, score))
        hits.sort(key=lambda item: (-item[1], item[0].title))
        return hits[:limit]

    def list_pages_by_kb(self, kb_id: str) -> list[WikiPageRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM pages WHERE kb_id=? AND status='active'", (kb_id,)
            ).fetchall()
        return [self._row_to_page(row) for row in rows]

    def stat(self, wiki_id: str) -> dict[str, Any]:
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pages WHERE wiki_id=?", (wiki_id,)
            ).fetchone()["c"]
            active = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pages WHERE wiki_id=? AND status='active'", (wiki_id,)
            ).fetchone()["c"]
            rows = self._conn.execute(
                "SELECT tags_json, links_json FROM pages WHERE wiki_id=? AND status='active'",
                (wiki_id,),
            ).fetchall()
        tags: dict[str, int] = {}
        link_count = 0
        for row in rows:
            page_tags = json.loads(row["tags_json"] or "[]")
            page_links = json.loads(row["links_json"] or "[]")
            link_count += len(page_links)
            for tag in page_tags:
                tags[tag] = tags.get(tag, 0) + 1
        return {
            "pageCount": total,
            "active": active,
            "deprecated": max(0, total - active),
            "linkCount": link_count,
            "tags": tags,
        }

    def export_lines(self, wiki_id: str) -> list[str]:
        records = self.list_pages(wiki_id, status="active")
        lines: list[str] = []
        for record in records:
            item = dict(record.to_dict())
            item["kind"] = "page"
            lines.append(json.dumps(item, ensure_ascii=False))
        return lines

    # ---------- jobs ----------

    def create_job(self, job_id: str, wiki_id: str, task: str, payload: dict[str, Any]) -> None:
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs(job_id, wiki_id, task, status, payload_json, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    job_id,
                    wiki_id,
                    task,
                    "pending",
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def update_job(
        self, job_id: str, *, status: str, result: dict[str, Any] | None = None, error: str = ""
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status=?, result_json=?, error=?, updated_at=? WHERE job_id=?",
                (
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error,
                    _now_iso(),
                    job_id,
                ),
            )
            self._conn.commit()

    def list_jobs(self, *, wiki_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        sql = "SELECT * FROM jobs"
        params: list[str] = []
        if wiki_id:
            sql += " WHERE wiki_id=?"
            params.append(wiki_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(str(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    # ---------- row 转换 ----------

    @staticmethod
    def _row_to_wiki(row: sqlite3.Row) -> WikiMeta:
        return WikiMeta(
            wiki_id=str(row["wiki_id"]),
            kb_id=str(row["kb_id"]),
            name=str(row["name"]),
            tenant_id=str(row["tenant_id"]),
            owner_id=str(row["owner_id"]),
            config=json.loads(row["config_json"] or "{}"),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_page(row: sqlite3.Row) -> WikiPageRecord:
        return WikiPageRecord(
            page_id=str(row["page_id"]),
            wiki_id=str(row["wiki_id"]),
            kb_id=str(row["kb_id"]),
            doc_id=str(row["doc_id"]),
            title=str(row["title"]),
            level=int(row["level"]),
            parent_page_id=str(row["parent_page_id"]),
            stable_key=str(row["stable_key"]),
            fields=json.loads(row["fields_json"] or "{}"),
            tags=json.loads(row["tags_json"] or "[]"),
            markdown=str(row["markdown"]),
            links=json.loads(row["links_json"] or "[]"),
            source_docs=json.loads(row["source_docs_json"] or "[]"),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "jobId": str(row["job_id"]),
            "wikiId": str(row["wiki_id"]),
            "task": str(row["task"]),
            "status": str(row["status"]),
            "payload": json.loads(row["payload_json"] or "{}"),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": str(row["error"] or ""),
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
        }
