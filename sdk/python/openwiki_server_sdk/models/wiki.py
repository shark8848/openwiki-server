"""Wiki 模型兼容层。

模型定义已归位到 ``ikc_sdk.core.models.wiki`` / ``wiki_engine``；本模块保留旧导入名，
使既有 ``openwiki-server-sdk`` 调用方无需改代码。新代码可直接使用 `ikc_sdk` 的规范名。
"""

from __future__ import annotations

from ikc_sdk.core.models.wiki import WikiPageNode, WikiPageView
from ikc_sdk.core.models.wiki_engine import (
    WikiEngineBuildResult,
    WikiEngineExportResponse,
    WikiEngineJobListResponse,
    WikiEngineJobView,
    WikiEngineListResponse,
    WikiEngineMetaView,
    WikiEngineOpResult,
    WikiEnginePageResult,
    WikiEngineSearchHit,
    WikiEngineSearchResponse,
    WikiEngineStatResponse,
    WikiEngineTreeResponse,
)

# 旧 SDK 类名 → 共享契约类（保持既有导入与属性访问兼容）。
WikiMeta = WikiEngineMetaView
WikiListData = WikiEngineListResponse
WikiTreeNode = WikiPageNode
WikiTreeData = WikiEngineTreeResponse
WikiPageDetail = WikiPageView
WikiPageData = WikiEnginePageResult
WikiSearchHit = WikiEngineSearchHit
WikiSearchData = WikiEngineSearchResponse
WikiStat = WikiEngineStatResponse
WikiExport = WikiEngineExportResponse
BuildResult = WikiEngineBuildResult
WikiJob = WikiEngineJobView
JobListData = WikiEngineJobListResponse
WikiOpResult = WikiEngineOpResult

__all__ = [
    "BuildResult",
    "JobListData",
    "WikiExport",
    "WikiEngineBuildResult",
    "WikiEngineExportResponse",
    "WikiEngineJobListResponse",
    "WikiEngineJobView",
    "WikiEngineListResponse",
    "WikiEngineMetaView",
    "WikiEngineOpResult",
    "WikiEnginePageResult",
    "WikiEngineSearchHit",
    "WikiEngineSearchResponse",
    "WikiEngineStatResponse",
    "WikiEngineTreeResponse",
    "WikiJob",
    "WikiListData",
    "WikiMeta",
    "WikiOpResult",
    "WikiPageData",
    "WikiPageDetail",
    "WikiPageNode",
    "WikiPageView",
    "WikiSearchData",
    "WikiSearchHit",
    "WikiStat",
    "WikiTreeData",
    "WikiTreeNode",
]
