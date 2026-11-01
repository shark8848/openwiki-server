"""TM envelope compatibility for openwiki Celery task bodies."""

from __future__ import annotations

import json

import pytest

from openwiki_engine.celery_tasks import handlers


class _Store:
    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    def update_job(self, job_id: str, **kwargs) -> None:
        self.jobs.append((job_id, kwargs))


class _Service:
    def __init__(self) -> None:
        self.store = _Store()
        self.calls: list[tuple[str, dict]] = []
        self.ensured: list[tuple[str, str]] = []
        self.fail = False

    def ensure_wiki(self, wiki_id: str, *, kb_id: str) -> dict:
        self.ensured.append((wiki_id, kb_id))
        return {"wikiId": wiki_id, "kbId": kb_id}

    def build_from_doc(self, wiki_id: str, **kwargs):
        self.calls.append((wiki_id, kwargs))
        if self.fail:
            raise RuntimeError("boom")
        return {"ok": True, "wikiId": wiki_id}

    def export(self, wiki_id: str, **kwargs):
        self.calls.append((wiki_id, kwargs))
        return {"ok": True, "wikiId": wiki_id}


@pytest.fixture()
def fake(monkeypatch):
    service = _Service()
    reports: list[tuple[str, dict]] = []
    monkeypatch.setattr(handlers, "get_service", lambda: service)
    monkeypatch.setattr(
        handlers,
        "_report",
        lambda op, **kwargs: reports.append((op, kwargs)),
    )
    return service, reports


def test_build_accepts_tm_envelope_and_reports_lifecycle(fake):
    service, reports = fake
    payload = json.dumps(
        {
            "body": {
                "wiki_id": "w-1",
                "kb_id": "kb-1",
                "doc_id": "d-1",
                "markdown": "# 标题",
                "taskId": "task-1",
                "taskStrategy": {"priority": 2},
            },
            "task_id": "task-1",
            "req_id": "req-1",
            "trace_id": "trace-1",
        },
        ensure_ascii=False,
    )

    assert handlers.build(payload) == {"ok": True, "wikiId": "w-1"}
    assert service.calls == [
        (
            "w-1",
            {
                "doc_id": "d-1",
                "title": "",
                "tags": [],
                "markdown": "# 标题",
                "markdown_file_id": "",
                "wiki_config": {},
            },
        )
    ]
    assert service.ensured == [("w-1", "kb-1")]
    assert [op for op, _ in reports] == ["begin", "end"]
    assert reports[0][1]["links"]["task_id"] == "task-1"


def test_native_flat_kwargs_still_work(fake):
    service, reports = fake

    assert handlers.export(wiki_id="w-2", format="json", job_id="job-2") == {
        "ok": True,
        "wikiId": "w-2",
    }
    assert service.calls == [("w-2", {"format": "json"})]
    assert service.store.jobs == [("job-2", {"status": "success", "result": {"ok": True, "wikiId": "w-2"}})]
    assert reports == []


def test_build_without_kb_id_keeps_legacy_native_behavior(fake):
    service, _reports = fake

    assert handlers.build(wiki_id="w-legacy", doc_id="d-1", markdown="# 标题") == {
        "ok": True,
        "wikiId": "w-legacy",
    }
    assert service.ensured == []


def test_tm_failure_reports_failed_end(fake):
    service, reports = fake
    service.fail = True
    payload = json.dumps(
        {"body": {"wiki_id": "w-3", "markdown": "x"}, "task_id": "task-3"},
        ensure_ascii=False,
    )

    with pytest.raises(RuntimeError, match="boom"):
        handlers.build(payload)

    assert [op for op, _ in reports] == ["begin", "end"]
    assert reports[-1][1]["succeeded"] is False
