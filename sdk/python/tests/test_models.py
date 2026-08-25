from __future__ import annotations

from openwiki_server_sdk.models.wiki import (
    BuildResult,
    WikiJob,
    WikiMeta,
    WikiPageData,
    WikiSearchData,
    WikiStat,
    WikiTreeData,
)


def test_wiki_meta_roundtrip():
    data = {
        "wikiId": "wiki_abc",
        "kbId": "kb_1",
        "name": "演示",
        "tenantId": "t1",
        "wikiConfig": {"granularity": "heading"},
        "status": "active",
        "createdAt": "2026-01-01T00:00:00Z",
        "future": "kept",
    }
    meta = WikiMeta.from_dict(data)
    assert meta.wikiId == "wiki_abc"
    assert meta.wikiConfig == {"granularity": "heading"}
    assert meta.extra == {"future": "kept"}
    assert meta.to_dict()["future"] == "kept"


def test_tree_data_nested_children():
    data = {
        "wikiId": "wiki_1",
        "kbId": "kb_1",
        "total": 1,
        "tree": [
            {"pageId": "p1", "title": "根", "level": 1, "children": [{"pageId": "p2", "title": "子", "level": 2}]}
        ],
    }
    tree = WikiTreeData.from_dict(data)
    assert tree.tree[0].children[0].pageId == "p2"


def test_page_data():
    data = {
        "kbId": "kb_1",
        "page": {"pageId": "p1", "title": "安装", "markdown": "# 安装", "tags": ["手册"], "sourceDocs": ["doc1"]},
    }
    page = WikiPageData.from_dict(data)
    assert page.page is not None
    assert page.page.sourceDocs == ["doc1"]
    assert page.page.title == "安装"


def test_search_stat_build_job_parsing():
    search = WikiSearchData.from_dict({"q": "x", "total": 1, "items": [{"pageId": "p", "title": "t", "score": 3.0}]})
    assert search.items[0].score == 3.0

    stat = WikiStat.from_dict({"pageCount": 5, "active": 5, "tags": {"a": 2}})
    assert stat.tags == {"a": 2}

    build = BuildResult.from_dict({"mode": "rule", "total": 2, "pages": [{"title": "p"}]})
    assert build.total == 2

    job = WikiJob.from_dict({"jobId": "job_1", "task": "build", "status": "success", "payload": {"docId": "d"}})
    assert job.status == "success"
    assert job.payload == {"docId": "d"}
