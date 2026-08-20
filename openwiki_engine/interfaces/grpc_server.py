"""gRPC 协议面：WikiService（wiki.v1）。

环境无 grpc-tools，采用运行时动态 descriptor（FileDescriptorProto + message_factory +
grpc generic handler）实现服务端与客户端；proto/wiki/v1/wiki.proto 为权威契约。
"""

from __future__ import annotations

import json
from concurrent import futures
from typing import Any, Callable

import grpc
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from ..errors import OpenWikiError
from ..protocol import error, new_trace_id, ok
from ..runtime import get_service

SERVICE_NAME = "wiki.v1.WikiService"
MESSAGE_NAME = "wiki.v1.Envelope"


def _build_pool() -> descriptor_pool.DescriptorPool:
    file_proto = descriptor_pb2.FileDescriptorProto()
    file_proto.name = "wiki/v1/wiki.proto"
    file_proto.package = "wiki.v1"
    file_proto.syntax = "proto3"
    envelope = file_proto.message_type.add()
    envelope.name = "Envelope"
    for name, number in (
        ("trace_id", 1),
        ("err_code", 2),
        ("err_msg", 3),
        ("data_json", 4),
    ):
        field = envelope.field.add()
        field.name = name
        field.number = number
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        field.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_proto)
    return pool


_pool = _build_pool()
Envelope = message_factory.GetMessageClass(_pool.FindMessageTypeByName(MESSAGE_NAME))


def _ser(msg: Any) -> bytes:
    return msg.SerializeToString()


def _deser(data: bytes) -> Any:
    msg = Envelope()
    msg.ParseFromString(data)
    return msg


# ---------- 方法分发 ----------

METHOD_HANDLERS: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {}


def _register(method: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        METHOD_HANDLERS[method] = fn
        return fn

    return decorator


@_register("CreateWiki")
def _create_wiki(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.create_wiki(
        wiki_id_value=str(p.get("wikiId") or ""),
        kb_id=str(p.get("kbId") or ""),
        name=str(p.get("name") or ""),
        tenant_id=str(p.get("tenantId") or ""),
        owner_id=str(p.get("ownerId") or ""),
        wiki_config=p.get("wikiConfig"),
    )


@_register("GetWiki")
def _get_wiki(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.get_wiki(str(p.get("wikiId") or ""))


@_register("DeleteWiki")
def _delete_wiki(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.delete_wiki(str(p.get("wikiId") or ""))


@_register("ListWikis")
def _list_wikis(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.list_wikis(
        tenant_id=str(p.get("tenantId") or ""), owner_id=str(p.get("ownerId") or "")
    )


@_register("BuildWiki")
def _build_wiki(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.build_from_doc(
        str(p.get("wikiId") or ""),
        doc_id=str(p.get("docId") or ""),
        title=str(p.get("title") or ""),
        tags=p.get("tags") or [],
        markdown=str(p.get("markdown") or ""),
        wiki_config=p.get("wikiConfig"),
    )


@_register("MergeRecords")
def _merge_records(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.merge_records(
        str(p.get("wikiId") or ""),
        pages=p.get("pages") or [],
        doc_id=str(p.get("docId") or ""),
    )


@_register("DeprecateDoc")
def _deprecate_doc(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.deprecate_doc(str(p.get("wikiId") or ""), doc_id=str(p.get("docId") or ""))


@_register("Tree")
def _tree(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.tree(
        str(p.get("wikiId") or ""),
        page=int(p.get("page") or 1),
        page_size=int(p.get("pageSize") or 20),
    )


@_register("Page")
def _page(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.page(str(p.get("wikiId") or ""), page_id_value=str(p.get("pageId") or ""))


@_register("Search")
def _search(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.search(
        str(p.get("wikiId") or ""),
        q=str(p.get("q") or ""),
        tag=str(p.get("tag") or ""),
        limit=int(p.get("limit") or 20),
    )


@_register("Stat")
def _stat(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.stat(str(p.get("wikiId") or ""))


@_register("ExportWiki")
def _export_wiki(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.export(str(p.get("wikiId") or ""), format=str(p.get("format") or "jsonl"))


@_register("UpdateWiki")
def _update_wiki(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.update_wiki(str(p.get("wikiId") or ""), message=str(p.get("message") or ""))


@_register("Ingest")
def _ingest(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.ingest(str(p.get("wikiId") or ""), connector=str(p.get("connector") or ""))


@_register("RunJob")
def _run_job(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.run_job(str(p.get("jobId") or ""))


@_register("GetJob")
def _get_job(service, p: dict[str, Any]) -> dict[str, Any]:
    return service.get_job(str(p.get("jobId") or ""))


# ---------- server ----------


def _make_handler(method: str, service: Any | None = None):
    def _call(request: Any, context: Any) -> Any:
        trace_id = request.trace_id or new_trace_id()
        try:
            data = json.loads(request.data_json or "{}")
            params = dict(data.get("params") or data)
            result = METHOD_HANDLERS[method](service or get_service(), params)
            payload = ok(trace_id, result)
        except OpenWikiError as exc:
            payload = error(trace_id, exc)
        except Exception as exc:  # pragma: no cover
            payload = error(trace_id, exc)
        resp = Envelope()
        resp.trace_id = payload["traceId"]
        resp.err_code = payload["errCode"]
        resp.err_msg = payload["errMsg"]
        resp.data_json = json.dumps(payload.get("data"), ensure_ascii=False, default=str)
        return resp

    return _call


def build_grpc_server(service: Any | None = None) -> grpc.Server:
    """构造 gRPC server（不启动），供 serve_grpc 与测试复用。"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    handlers = {
        method: grpc.unary_unary_rpc_method_handler(
            _make_handler(method, service), request_deserializer=_deser, response_serializer=_ser
        )
        for method in METHOD_HANDLERS
    }
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(SERVICE_NAME, handlers),))
    return server


def serve_grpc(host: str = "0.0.0.0", port: int = 50052, service: Any | None = None) -> int:
    """启动 gRPC 服务（阻塞），返回实际监听端口。"""
    server = build_grpc_server(service)
    bound_port = server.add_insecure_port(f"{host}:{port}")
    server.start()
    print(f"[openwiki-server] gRPC listening on {host}:{bound_port} ({SERVICE_NAME})")
    server.wait_for_termination()
    return bound_port


# ---------- client ----------


def grpc_client(host: str = "localhost", port: int = 50052) -> Callable[..., dict[str, Any]]:
    """返回通用调用函数：client(method, params, trace_id="") → envelope dict。"""
    channel = grpc.insecure_channel(f"{host}:{port}")

    def call(method: str, params: dict[str, Any] | None = None, trace_id: str = "") -> dict[str, Any]:
        req = Envelope()
        req.trace_id = trace_id or new_trace_id()
        req.data_json = json.dumps({"params": params or {}}, ensure_ascii=False)
        stub = channel.unary_unary(
            f"/{SERVICE_NAME}/{method}", request_serializer=_ser, response_deserializer=_deser
        )
        resp = stub(req)
        return {
            "traceId": resp.trace_id,
            "errCode": resp.err_code,
            "errMsg": resp.err_msg,
            "data": json.loads(resp.data_json) if resp.data_json else None,
        }

    return call
