from __future__ import annotations

from dataclasses import dataclass, field

from ikc_sdk.core.headers import (
    HEADER_TENANT_ID,
    HEADER_USER_ID,
    HEADER_USER_ROLES,
    TRACE_HEADER_NAMES,
)

from ._version import __version__


@dataclass
class CallerIdentity:
    """调用方身份上下文；仅非空字段透传为请求头（与 open-ikc SDK 约定一致）。"""

    user_id: str | None = None
    tenant_id: str | None = None
    roles: list[str] | None = None


def build_headers(
    *,
    token: str | None,
    trace_id: str,
    identity: CallerIdentity | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """构建请求头：认证、trace 与身份头；extra_headers 优先级最高。"""
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": f"openwiki-server-sdk/{__version__}",
        TRACE_HEADER_NAMES[0]: trace_id,
        TRACE_HEADER_NAMES[1]: trace_id,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if identity:
        if identity.user_id:
            headers[HEADER_USER_ID] = identity.user_id
        if identity.tenant_id:
            headers[HEADER_TENANT_ID] = identity.tenant_id
        if identity.roles:
            headers[HEADER_USER_ROLES] = ",".join(identity.roles)
    if extra_headers:
        headers.update(extra_headers)
    return headers
