"""OpenWiki 内核适配层。

- CLI 子进程调用：`openwiki personal --update`（非交互自动退出），HOME 指向 wiki
  实例根目录实现多租户隔离（openwiki 配置目录为 ~/.openwiki）；
- OKF v0.2 Markdown 解析：front matter（type/tags/sources/status/扩展字段）+ 正文 +
  页面互链；
- 规则切页生成：LLM/内核不可用时按 wikiConfig.granularity 确定性切页，保证离线可用。

所有 openwiki 相关导入/调用均为守卫式，核心能力不依赖其可用性。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..config import Settings

logger = logging.getLogger("openwiki_engine.openwiki")

RESERVED_DOCS = {"index.md", "log.md"}
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]|]+)?\]\]")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
FIELD_RE = re.compile(r"^\s*([\u4e00-\u9fa5\w]+)[：:]\s*(.+?)\s*$")


def _json_safe(value: Any) -> Any:
    """YAML front matter 的日期/时间归一化为 ISO 字符串，避免响应序列化失败。"""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def openwiki_bin(settings: Settings | None = None) -> str:
    settings = settings or Settings()
    return settings.openwiki_bin_resolved()


def openwiki_available(settings: Settings | None = None) -> bool:
    settings = settings or Settings()
    if not settings.openwiki_enabled:
        return False
    binary = openwiki_bin(settings)
    if "/" in binary:
        return Path(binary).exists()
    return shutil.which(binary) is not None


def run_update(
    wiki_root: str,
    *,
    provider: str = "openai",
    model_id: str = "",
    message: str = "",
    timeout: int = 600,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """运行 `openwiki personal --update <message>`（非交互，stdin 关闭自动退出）。"""
    wiki_root = os.path.abspath(wiki_root)
    binary = openwiki_bin(settings)
    cmd = [binary, "personal", "--update"]
    if message:
        cmd.append(message)
    env = dict(os.environ)
    env.update(
        {
            "HOME": wiki_root,
            "OPENWIKI_TELEMETRY_DISABLED": "1",
            "OPENWIKI_PROVIDER": provider,
        }
    )
    if model_id:
        env["OPENWIKI_MODEL_ID"] = model_id
    try:
        Path(wiki_root).mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            cmd,
            cwd=wiki_root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("openwiki update 超时（%ss）：%s", timeout, wiki_root)
        return {"ok": False, "reason": f"openwiki update 超时（{timeout}s）", "returncode": -1}
    except FileNotFoundError:
        return {"ok": False, "reason": "openwiki 可执行文件不存在", "returncode": -1}
    ok_flag = proc.returncode == 0
    if not ok_flag:
        logger.warning(
            "openwiki update 失败 rc=%s：%s", proc.returncode, (proc.stderr or proc.stdout)[-2000:]
        )
    return {
        "ok": ok_flag,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
    }


def run_ingest(
    wiki_root: str,
    connector: str,
    *,
    settings: Settings | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """运行 `openwiki ingest <connector>`。"""
    wiki_root = os.path.abspath(wiki_root)
    binary = openwiki_bin(settings)
    cmd = [binary, "ingest", connector]
    env = dict(os.environ)
    env.update({"HOME": wiki_root, "OPENWIKI_TELEMETRY_DISABLED": "1"})
    try:
        Path(wiki_root).mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            cmd,
            cwd=wiki_root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"openwiki ingest 超时（{timeout}s）", "returncode": -1}
    except FileNotFoundError:
        return {"ok": False, "reason": "openwiki 可执行文件不存在", "returncode": -1}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
    }


# ---------- OKF 解析 ----------


def _parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    """解析 YAML front matter 最小子集（key: value / 数组 / 内联对象），缺省降级为空 dict。"""
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw) or {}
        return (data if isinstance(data, dict) else {}), raw
    except Exception:
        pass
    fields: dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
        fields[key] = value
    return fields, raw


def _extract_links(markdown: str, kb_id: str) -> list[dict[str, str]]:
    from ..domain.ids import normalize_title, page_id

    links: list[dict[str, str]] = []
    for match in WIKI_LINK_RE.findall(markdown):
        title = match.strip()
        if title:
            links.append({"title": title, "pageId": page_id(kb_id, normalize_title(title))})
    for title, target in MD_LINK_RE.findall(markdown):
        target = target.strip()
        if target in RESERVED_DOCS:
            continue
        stable_key = normalize_title(target.rsplit("/", 1)[-1].removesuffix(".md"))
        links.append({"title": title.strip() or stable_key, "pageId": page_id(kb_id, stable_key)})
    dedup: dict[str, dict[str, str]] = {}
    for link in links:
        dedup[link["title"]] = link
    return sorted(dedup.values(), key=lambda item: item["title"])


def _source_docs(front: dict[str, Any]) -> list[str]:
    sources = front.get("sources") or []
    doc_ids: list[str] = []
    for item in sources if isinstance(sources, list) else [sources]:
        if isinstance(item, dict):
            value = str(item.get("docId") or item.get("doc_id") or item.get("id") or "").strip()
        else:
            value = str(item).strip()
        if value and value not in doc_ids:
            doc_ids.append(value)
    return doc_ids


def parse_okf_pages(wiki_dir: str, *, kb_id: str = "") -> list[dict[str, Any]]:
    """扫描 OKF Markdown 目录，返回页面数据 dict 列表（index.md/log.md 跳过）。"""
    root = Path(wiki_dir)
    if not root.exists():
        return []
    pages: list[dict[str, Any]] = []
    for path in sorted(root.glob("**/*.md")):
        if path.name in RESERVED_DOCS or path.name.startswith("."):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        front: dict[str, Any] = {}
        body = text
        match = FRONT_MATTER_RE.match(text)
        if match:
            front, _ = _parse_front_matter(match.group(1))
            body = match.group(2).strip()
        title = str(front.get("title") or "").strip() or path.stem
        stable_key = str(front.get("stableKey") or "").strip() or path.stem
        fields = {
            str(key).strip(): value
            for key, value in front.items()
            if str(key) not in ("title", "type", "generated", "tags", "sources", "status", "stale_after", "stableKey")
        }
        fields = {key: _json_safe(value) for key, value in fields.items()}
        status = str(front.get("status") or "active").strip().lower()
        if status not in ("active", "deprecated"):
            status = "active"
        pages.append(
            {
                "file": str(path.relative_to(root)),
                "title": title,
                "stableKey": stable_key,
                "type": str(front.get("type") or "concept"),
                "tags": [str(x) for x in (front.get("tags") or []) if str(x).strip()],
                "fields": fields,
                "sourceDocs": _source_docs(front),
                "status": status,
                "markdown": body,
                "links": _extract_links(body, kb_id) if kb_id else [],
            }
        )
    return pages


# ---------- 规则切页（离线降级） ----------


def extract_fields(markdown: str, keys: list[str]) -> dict[str, Any]:
    """按 extractFields 白名单抽取结构化字段（`字段：值` 行）。"""
    if not keys:
        return {}
    found: dict[str, Any] = {}
    for line in markdown.splitlines():
        match = FIELD_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip()
        if key in keys:
            found[key] = match.group(2).strip()
    return found


def _heading_level(line: str) -> int:
    level = len(line) - len(line.lstrip("#"))
    return level if 1 <= level <= 6 else 0


def generate_pages_rule(
    markdown: str,
    *,
    title: str,
    tags: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """按 granularity 确定性切页：
    - page：整文档一页；
    - heading/section：按 h1/h2 标题切页（h1 为根页，h2 挂 h1 之下）；
    - auto：有 h1 按 section，否则按 heading，无标题回退 page。
    返回页面 dict（不含 pageId，由 service 派生稳定 ID）。
    """
    config = dict(config or {})
    granularity = str(config.get("granularity") or "auto").lower()
    extract_keys = [str(x) for x in (config.get("extractFields") or [])]
    tags = list(tags or [])
    text = markdown.strip()
    if not text:
        text = f"# {title}"

    if granularity == "page" or granularity == "auto" and not re.search(r"^#{1,2}\s", text, re.MULTILINE):
        stable_key = title.strip() or "未命名页面"
        return [
            {
                "title": title.strip() or "未命名页面",
                "stableKey": stable_key,
                "level": 1,
                "parentStableKey": "",
                "tags": tags,
                "fields": extract_fields(text, extract_keys),
                "markdown": text,
            }
        ]

    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    stack: list[dict[str, Any]] = []
    for line in lines:
        level = _heading_level(line)
        if level in (1, 2):
            heading_text = line.lstrip("#").strip()
            current = {
                "title": heading_text or "未命名章节",
                "stableKey": heading_text,
                "level": level,
                "parentStableKey": "",
                "tags": tags,
                "fields": {},
                "markdown": [line],
            }
            sections.append(current)
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            if stack:
                current["parentStableKey"] = stack[-1]["stableKey"]
            stack.append(current)
        elif current is not None:
            current["markdown"].append(line)
        elif line.strip():
            current = {
                "title": title.strip() or "未命名页面",
                "stableKey": title,
                "level": 1,
                "parentStableKey": "",
                "tags": tags,
                "fields": {},
                "markdown": [line],
            }
            sections.append(current)
            stack = [current]

    if not sections:
        return generate_pages_rule(text, title=title, tags=tags, config={**config, "granularity": "page"})

    for section in sections:
        section["markdown"] = "\n".join(section["markdown"]).strip()
        section["fields"] = extract_fields(section["markdown"], extract_keys)
    return sections
