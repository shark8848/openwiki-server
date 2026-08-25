"""openwiki-server-sdk 同步全链路冒烟：创建实例 → 真实文档建页 → 查询/检索/导出 → 异步 job → 清理。

前置：独立承载服务已启动（默认 127.0.0.1:18011，离线规则模式可免 LLM/网络）。
运行：python sdk/python/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from openwiki_server_sdk import OpenWikiServerClient

ROOT = Path(__file__).resolve().parents[3]  # sdk/python/examples -> 仓库根


def main() -> int:
    base_url = "http://127.0.0.1:18011"
    suffix = sys.argv[1] if len(sys.argv) > 1 else "sdk"
    with OpenWikiServerClient(base_url=base_url) as client:
        # 1. 创建 wiki 实例
        wiki = client.wikis.create(
            kbId=f"kb_sdk_{suffix}",
            name="SDK 联调冒烟",
            tenantId="t1",
            wikiConfig={"granularity": "heading"},
        )
        print(f"[1] 创建 wiki -> wikiId={wiki.wikiId}")

        # 2. 用仓库真实文档建页（规则切页，确定性）
        result = client.wikis.build(
            wiki.wikiId,
            docId="doc_1",
            title="任务进展记录",
            tags=["运维", "进展"],
            markdown=(ROOT / "docs" / "进展.md").read_text(encoding="utf-8"),
        )
        print(f"[2] build -> mode={result.mode} total={result.total}")

        # 3. 查询：树 / 检索 / 统计 / 导出
        tree = client.wikis.tree(wiki.wikiId)
        print(f"[3] tree -> total={tree.total} roots={[n.title for n in tree.tree[:3]]}")

        hits = client.wikis.search(wiki.wikiId, q="HAProxy")
        print(f"[4] search -> total={hits.total}")

        stat = client.wikis.stat(wiki.wikiId)
        print(f"[5] stat -> pageCount={stat.pageCount} tags={stat.tags}")

        export = client.wikis.export(wiki.wikiId, format="json")
        print(f"[6] export -> format={export.format} total={export.total}")

        # 4. 异步任务：提交 → 手动执行 → 查询
        job = client.wikis.build(wiki.wikiId, docId="doc_async", title="异步示例", markdown="# 异步示例", async_=True)
        print(f"[7] submit async job -> jobId={job.jobId} status={job.status}")
        job = client.jobs.run(job.jobId)
        print(f"[8] run job -> status={job.status}")

        # 5. 运行时自检：接口目录
        catalog = client.fetch_openapi()
        print(f"[9] openapi -> {len(catalog.get('paths', {}))} 个路径")

        # 6. 清理
        client.wikis.delete(wiki.wikiId)
        print(f"[10] delete -> wikiId={wiki.wikiId}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
