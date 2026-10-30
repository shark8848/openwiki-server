from __future__ import annotations

from ikc_sdk.core.trace import generate_trace_id


def ensure_trace_id(trace_id: str | None) -> str:
    """复用调用方显式传入的 traceId，否则生成新的。"""
    if trace_id:
        return str(trace_id)
    return generate_trace_id()


__all__ = ["ensure_trace_id", "generate_trace_id"]
