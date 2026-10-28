from __future__ import annotations

import importlib

import yaml
from celery import Task

from openwiki_engine.celery_tasks import MANIFEST_PATH


EXPECTED_TASKS = {
    "openwiki_server.build",
    "openwiki_server.merge",
    "openwiki_server.deprecate_doc",
    "openwiki_server.export",
    "openwiki_server.update",
    "openwiki_server.ingest",
}


def test_registrar_manifest_matches_task_package_contract():
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    tasks = data["tasks"]

    assert {item["task_name"] for item in tasks} == EXPECTED_TASKS
    for item in tasks:
        assert item["queue"] == "openwiki_server"
        assert item["bind"] is False
        module = importlib.import_module(item["module"])
        fn = getattr(module, item["function"])
        assert callable(fn)
        assert not isinstance(fn, Task)
