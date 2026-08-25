"""openwiki-server-sdk 异步客户端冒烟：创建实例 → 建页 → 查询 → 清理。

运行：python sdk/python/examples/async_quickstart.py
"""

from __future__ import annotations

import asyncio

from openwiki_server_sdk import AsyncOpenWikiServerClient


async def main() -> int:
    async with AsyncOpenWikiServerClient(base_url="http://127.0.0.1:18011") as client:
        wiki = await client.wikis.create(kbId="kb_sdk_async", name="异步冒烟", wikiConfig={"granularity": "page"})
        print(f"[1] create -> {wiki.wikiId}")

        result = await client.wikis.build(wiki.wikiId, docId="doc1", title="异步页", markdown="异步正文。")
        print(f"[2] build -> mode={result.mode} total={result.total}")

        tree = await client.wikis.tree(wiki.wikiId)
        print(f"[3] tree -> total={tree.total}")

        stat = await client.wikis.stat(wiki.wikiId)
        print(f"[4] stat -> pageCount={stat.pageCount}")

        await client.wikis.delete(wiki.wikiId)
        print("[5] delete ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
