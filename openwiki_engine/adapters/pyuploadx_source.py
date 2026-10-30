"""PyUploadX 文件源适配：按 file_id 下载 Wiki Markdown 原文。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ..config import Settings
from ..errors import INTERNAL, InvalidParamsError, OpenWikiError


def _build_client(settings: Settings):
    try:
        from pyuploadx import Client
    except Exception as exc:  # pragma: no cover - 依赖缺失时给出可读错误
        raise OpenWikiError(
            INTERNAL, "PyUploadX SDK 未安装或导入失败", field="markdownFileId"
        ) from exc

    api_key = settings.pyuploadx_api_key or None
    bearer_token = settings.pyuploadx_bearer_token or None
    if not api_key and not bearer_token:
        raise OpenWikiError(
            INTERNAL,
            "PyUploadX 未配置认证（PYUPLOADX_API_KEY / PYUPLOADX_BEARER_TOKEN）",
            field="markdownFileId",
        )
    return Client(
        base_url=settings.pyuploadx_base_url,
        api_key=api_key,
        bearer_token=bearer_token,
        state_dir=settings.pyuploadx_state_dir,
        timeout=settings.pyuploadx_timeout,
    )


def download_markdown(file_id: str, settings: Settings) -> str:
    """下载 PyUploadX 文件并返回 UTF-8 Markdown 文本（临时文件用后删除）。"""
    file_id = file_id.strip()
    if not file_id:
        raise InvalidParamsError("文件 ID 不能为空", field="markdownFileId")

    path: Path | None = None
    try:
        client = _build_client(settings)
        fd, name = tempfile.mkstemp(prefix="openwiki-source-", suffix=".md")
        os.close(fd)
        path = Path(name)
        with client:
            client.download(file_id, str(path))
        size = path.stat().st_size
        if size <= 0:
            raise InvalidParamsError(
                "PyUploadX 文件内容为空", field="markdownFileId", reason=file_id
            )
        if size > settings.wiki_source_max_bytes:
            raise InvalidParamsError(
                "PyUploadX 文件超过 Wiki 原文大小上限",
                field="markdownFileId",
                reason=f"size={size}, max={settings.wiki_source_max_bytes}",
            )
        try:
            markdown = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidParamsError(
                "PyUploadX 文件不是 UTF-8 Markdown", field="markdownFileId"
            ) from exc
        if not markdown.strip():
            raise InvalidParamsError(
                "PyUploadX 文件内容为空", field="markdownFileId", reason=file_id
            )
        return markdown
    except (InvalidParamsError, OpenWikiError):
        raise
    except Exception as exc:  # noqa: BLE001 - PyUploadX/httpx 异常统一转引擎错误
        status = int(getattr(exc, "status_code", 0) or 0)
        if status in (404, 410):
            raise InvalidParamsError(
                "PyUploadX 文件不存在或已过期", field="markdownFileId", reason=file_id
            ) from exc
        if status in (401, 403):
            raise OpenWikiError(
                INTERNAL, "PyUploadX 鉴权失败", field="markdownFileId", reason=str(exc)
            ) from exc
        raise OpenWikiError(
            INTERNAL, f"PyUploadX 文件下载失败：{exc}", field="markdownFileId"
        ) from exc
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


__all__ = ["download_markdown"]
