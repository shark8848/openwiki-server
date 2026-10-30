from __future__ import annotations

import os
from pathlib import Path

import pytest

from openwiki_engine.adapters import pyuploadx_source
from openwiki_engine.config import Settings
from openwiki_engine.errors import InvalidParamsError, OpenWikiError


class _Client:
    def __init__(self, *, content: bytes = b"", error: Exception | None = None) -> None:
        self.content = content
        self.error = error

    def __enter__(self) -> "_Client":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def download(self, file_id: str, destination: str) -> Path:
        if self.error is not None:
            raise self.error
        target = Path(destination)
        target.write_bytes(self.content)
        return target


def _settings() -> Settings:
    return Settings(pyuploadx_api_key="test-key")


def test_download_markdown_reads_utf8_sig_and_removes_temp_file(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"")

    def fake_mkstemp(*, prefix: str, suffix: str) -> tuple[int, str]:
        assert prefix == "openwiki-source-"
        assert suffix == ".md"
        return os.open(source, os.O_RDWR), str(source)

    monkeypatch.setattr(pyuploadx_source.tempfile, "mkstemp", fake_mkstemp)
    monkeypatch.setattr(
        pyuploadx_source,
        "_build_client",
        lambda settings: _Client(content="\ufeff# 标题\n\n正文".encode("utf-8")),
    )

    assert pyuploadx_source.download_markdown("file-1", _settings()) == "# 标题\n\n正文"
    assert not source.exists()


def test_download_markdown_does_not_create_temp_before_client_is_ready(monkeypatch) -> None:
    called = False

    def fake_mkstemp(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("client 初始化失败时不应创建临时文件")

    def broken_client(settings):
        raise OpenWikiError("200500", "client unavailable")

    monkeypatch.setattr(pyuploadx_source.tempfile, "mkstemp", fake_mkstemp)
    monkeypatch.setattr(pyuploadx_source, "_build_client", broken_client)

    with pytest.raises(OpenWikiError):
        pyuploadx_source.download_markdown("file-1", _settings())
    assert called is False


@pytest.mark.parametrize("status", [404, 410])
def test_download_markdown_maps_missing_file(status, monkeypatch) -> None:
    error = RuntimeError("missing")
    error.status_code = status
    monkeypatch.setattr(pyuploadx_source, "_build_client", lambda settings: _Client(error=error))

    with pytest.raises(InvalidParamsError):
        pyuploadx_source.download_markdown("file-1", _settings())


def test_download_markdown_rejects_empty_and_oversized_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pyuploadx_source, "_build_client", lambda settings: _Client(content=b""))
    with pytest.raises(InvalidParamsError):
        pyuploadx_source.download_markdown("file-1", _settings())

    monkeypatch.setattr(
        pyuploadx_source,
        "_build_client",
        lambda settings: _Client(content=b"12345"),
    )
    with pytest.raises(InvalidParamsError):
        pyuploadx_source.download_markdown(
            "file-1", Settings(pyuploadx_api_key="test-key", wiki_source_max_bytes=4)
        )
