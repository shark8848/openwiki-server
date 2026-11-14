"""OpenWiki CLI 适配层：失败分类、完整日志与 connector 开关注入。"""

from __future__ import annotations

import stat
from pathlib import Path

from openwiki_engine.adapters.openwiki import _classify_failure, run_update
from openwiki_engine.config import Settings


def _fake_binary(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "openwiki-fake"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _settings(tmp_path: Path, binary: Path) -> Settings:
    return Settings(data_dir=str(tmp_path), openwiki_enabled=True, openwiki_bin=str(binary))


def _logs(wiki_root: Path) -> list[Path]:
    return sorted((wiki_root / ".openwiki" / "logs").glob("update-*.log"))


def test_run_update_writes_full_log_and_classifies_connector_failure(tmp_path):
    binary = _fake_binary(
        tmp_path,
        "echo 'stdout marker'\n"
        "echo 'custom-mcp MCP connector is not enabled.' >&2\n"
        "echo \"connectors=$OPENWIKI_DISABLE_CONNECTORS\" >&2\n"
        "exit 1\n",
    )
    wiki_root = tmp_path / "wikis" / "wiki_x"

    result = run_update(str(wiki_root), model_id="qwen3-30b-a3b", settings=_settings(tmp_path, binary))

    assert result["ok"] is False
    assert result["failure"] == "connector"
    log_path = Path(result["log"])
    assert log_path.is_file()
    text = log_path.read_text(encoding="utf-8")
    assert "stdout marker" in text
    assert "custom-mcp MCP connector is not enabled." in text
    # 引擎默认注入开关，不依赖镜像里的包装脚本
    assert "connectors=1" in text
    # 返回值只留 4000 字符，完整内容必须落盘
    assert len(text) > len(result["stderr"])


def test_run_update_success_keeps_failure_empty(tmp_path):
    binary = _fake_binary(tmp_path, "echo ok\nexit 0\n")
    wiki_root = tmp_path / "wikis" / "wiki_ok"

    result = run_update(str(wiki_root), settings=_settings(tmp_path, binary))

    assert result["ok"] is True
    assert result["failure"] == ""
    assert _logs(wiki_root)


def test_classify_failure_categories():
    assert _classify_failure("custom-mcp MCP connector is not enabled.", "") == "connector"
    assert (
        _classify_failure("Received empty response from chat model call.", "")
        == "empty-model-output"
    )
    assert _classify_failure("command timed out", "") == "timeout"
    assert _classify_failure("HTTP 401 Unauthorized", "") == "auth"
    assert _classify_failure("segfault", "") == "unknown"
