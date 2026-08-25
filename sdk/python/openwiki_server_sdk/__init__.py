from __future__ import annotations

import logging

from ._version import __version__
from ._bootstrap import async_client_from_env, client_from_env
from .async_client import AsyncOpenWikiServerClient
from .client import OpenWikiServerClient
from .envelope import Envelope
from .errors import (
    OpenWikiServerAPIError,
    OpenWikiServerBusinessError,
    OpenWikiServerConflictError,
    OpenWikiServerConnectionError,
    OpenWikiServerError,
    OpenWikiServerHTTPStatusError,
    OpenWikiServerNotFoundError,
    OpenWikiServerProtocolError,
    OpenWikiServerSystemError,
    OpenWikiServerTimeoutError,
    OpenWikiServerTransportError,
    OpenWikiServerValidationError,
)
from .headers import CallerIdentity
from .models.wiki import (
    BuildResult,
    JobListData,
    WikiExport,
    WikiJob,
    WikiListData,
    WikiMeta,
    WikiOpResult,
    WikiPageData,
    WikiPageDetail,
    WikiSearchData,
    WikiSearchHit,
    WikiStat,
    WikiTreeData,
    WikiTreeNode,
)
from .trace import generate_trace_id

__all__ = [
    "OpenWikiServerClient",
    "AsyncOpenWikiServerClient",
    "client_from_env",
    "async_client_from_env",
    "Envelope",
    "CallerIdentity",
    "WikiMeta",
    "WikiListData",
    "WikiOpResult",
    "WikiTreeNode",
    "WikiTreeData",
    "WikiPageDetail",
    "WikiPageData",
    "WikiSearchHit",
    "WikiSearchData",
    "WikiStat",
    "WikiExport",
    "BuildResult",
    "WikiJob",
    "JobListData",
    "generate_trace_id",
    "OpenWikiServerError",
    "OpenWikiServerTransportError",
    "OpenWikiServerConnectionError",
    "OpenWikiServerTimeoutError",
    "OpenWikiServerProtocolError",
    "OpenWikiServerHTTPStatusError",
    "OpenWikiServerAPIError",
    "OpenWikiServerValidationError",
    "OpenWikiServerNotFoundError",
    "OpenWikiServerConflictError",
    "OpenWikiServerSystemError",
    "OpenWikiServerBusinessError",
    "__version__",
]


def set_log_level(level: int | str) -> None:
    """设置 SDK 日志级别（默认 WARNING）。"""
    logging.getLogger("openwiki_server_sdk").setLevel(level)
