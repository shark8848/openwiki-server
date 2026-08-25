"""MCP 协议面：stdio JSON-RPC 服务（MCP 最小实现）。

支持 initialize / tools/list / tools/call，工具与 HTTP/gRPC 语义一一对应。
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from ..errors import OpenWikiError
from ..protocol import error, new_trace_id, ok
from ..runtime import get_service

SERVER_INFO = {"name": "openwiki-server", "version": "0.2.0"}
PROTOCOL_VERSION = "2025-03-26"


def _text_content(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


TOOLS: list[dict[str, Any]] = [
    {
        "name": "wiki_create",
        "description": "创建 wiki 实例（含 wikiConfig 校验）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wikiId": {"type": "string"},
                "kbId": {"type": "string"},
                "name": {"type": "string"},
                "tenantId": {"type": "string"},
                "ownerId": {"type": "string"},
                "wikiConfig": {"type": "object"},
            },
            "required": ["kbId"],
        },
    },
    {"name": "wiki_list", "description": "列出 wiki 实例", "inputSchema": {"type": "object", "properties": {"tenantId": {"type": "string"}, "ownerId": {"type": "string"}}}},
    {"name": "wiki_get", "description": "查询 wiki 实例元信息", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}}, "required": ["wikiId"]}},
    {"name": "wiki_delete", "description": "删除 wiki 实例（级联删除页面与文件）", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}}, "required": ["wikiId"]}},
    {"name": "wiki_tree", "description": "库级页面树", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "page": {"type": "integer"}, "pageSize": {"type": "integer"}}, "required": ["wikiId"]}},
    {"name": "wiki_page", "description": "页面详情", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "pageId": {"type": "string"}}, "required": ["wikiId", "pageId"]}},
    {"name": "wiki_search", "description": "页面检索（q + tag 过滤）", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "q": {"type": "string"}, "tag": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["wikiId"]}},
    {"name": "wiki_stat", "description": "wiki 统计", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}}, "required": ["wikiId"]}},
    {"name": "wiki_export", "description": "导出页面（jsonl/json）", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "format": {"type": "string"}}, "required": ["wikiId"]}},
    {"name": "wiki_build", "description": "按文档建页（markdown + title + tags + wikiConfig）", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "docId": {"type": "string"}, "title": {"type": "string"}, "tags": {"type": "array"}, "markdown": {"type": "string"}, "wikiConfig": {"type": "object"}}, "required": ["wikiId"]}},
    {"name": "wiki_merge", "description": "页面记录增量合并", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "pages": {"type": "array"}, "docId": {"type": "string"}}, "required": ["wikiId"]}},
    {"name": "wiki_deprecate_doc", "description": "按 docId 增量废弃", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "docId": {"type": "string"}}, "required": ["wikiId", "docId"]}},
    {"name": "wiki_update", "description": "OpenWiki 全量刷新（LLM 合成）", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "message": {"type": "string"}}, "required": ["wikiId"]}},
    {"name": "wiki_ingest", "description": "连接器摄取（git-repo/web-search/notion/...）", "inputSchema": {"type": "object", "properties": {"wikiId": {"type": "string"}, "connector": {"type": "string"}}, "required": ["wikiId", "connector"]}},
    {"name": "wiki_job_run", "description": "同步执行任务", "inputSchema": {"type": "object", "properties": {"jobId": {"type": "string"}}, "required": ["jobId"]}},
    {"name": "wiki_job_get", "description": "查询任务状态", "inputSchema": {"type": "object", "properties": {"jobId": {"type": "string"}}, "required": ["jobId"]}},
]


def _tool_handlers(service: Any) -> dict[str, Callable[..., dict[str, Any]]]:
    return {
        "wiki_create": lambda p: service.create_wiki(
            wiki_id_value=str(p.get("wikiId") or ""),
            kb_id=str(p.get("kbId") or ""),
            name=str(p.get("name") or ""),
            tenant_id=str(p.get("tenantId") or ""),
            owner_id=str(p.get("ownerId") or ""),
            wiki_config=p.get("wikiConfig"),
        ),
        "wiki_list": lambda p: service.list_wikis(tenant_id=str(p.get("tenantId") or ""), owner_id=str(p.get("ownerId") or "")),
        "wiki_get": lambda p: service.get_wiki(str(p.get("wikiId") or "")),
        "wiki_delete": lambda p: service.delete_wiki(str(p.get("wikiId") or "")),
        "wiki_tree": lambda p: service.tree(str(p.get("wikiId") or ""), page=int(p.get("page") or 1), page_size=int(p.get("pageSize") or 20)),
        "wiki_page": lambda p: service.page(str(p.get("wikiId") or ""), page_id_value=str(p.get("pageId") or "")),
        "wiki_search": lambda p: service.search(str(p.get("wikiId") or ""), q=str(p.get("q") or ""), tag=str(p.get("tag") or ""), limit=int(p.get("limit") or 20)),
        "wiki_stat": lambda p: service.stat(str(p.get("wikiId") or "")),
        "wiki_export": lambda p: service.export(str(p.get("wikiId") or ""), format=str(p.get("format") or "jsonl")),
        "wiki_build": lambda p: service.build_from_doc(
            str(p.get("wikiId") or ""),
            doc_id=str(p.get("docId") or ""),
            title=str(p.get("title") or ""),
            tags=p.get("tags") or [],
            markdown=str(p.get("markdown") or ""),
            wiki_config=p.get("wikiConfig"),
        ),
        "wiki_merge": lambda p: service.merge_records(str(p.get("wikiId") or ""), pages=p.get("pages") or [], doc_id=str(p.get("docId") or "")),
        "wiki_deprecate_doc": lambda p: service.deprecate_doc(str(p.get("wikiId") or ""), doc_id=str(p.get("docId") or "")),
        "wiki_update": lambda p: service.update_wiki(str(p.get("wikiId") or ""), message=str(p.get("message") or "")),
        "wiki_ingest": lambda p: service.ingest(str(p.get("wikiId") or ""), connector=str(p.get("connector") or "")),
        "wiki_job_run": lambda p: service.run_job(str(p.get("jobId") or "")),
        "wiki_job_get": lambda p: service.get_job(str(p.get("jobId") or "")),
    }


def _handle_request(req: dict[str, Any], handlers: dict[str, Callable]) -> dict[str, Any] | None:
    method = str(req.get("method") or "")
    req_id = req.get("id")
    if req_id is None:
        return None  # notification，无需响应
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = dict(req.get("params") or {})
        tool = str(params.get("name") or "")
        args = dict(params.get("arguments") or {})
        handler = handlers.get(tool)
        if handler is None:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"未知工具：{tool}"}}
        try:
            result = handler(args)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": _text_content(json.dumps(result, ensure_ascii=False, default=str))}}
        except OpenWikiError as exc:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": exc.message, "data": exc.detail()}}
        except Exception as exc:  # pragma: no cover
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"未知方法：{method}"}}


def serve_mcp(service: Any | None = None) -> None:
    """阻塞读取 stdin 的 MCP stdio 服务。"""
    svc = service or get_service()
    handlers = _tool_handlers(svc)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle_request(req, handlers)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve_mcp()
