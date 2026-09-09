# OKF 知识管理业务规范

> **文档定位**：面向业务人员（产品、知识运营、业务方研发）的「知识库 → 知识页面」业务规范。它把三件事放在一张纸上讲清楚：
>
> 1. **Google Open Knowledge Format（OKF）v0.2**：业界约定的「机器可读 Markdown 知识包」数据规范；
> 2. **LangChain OpenWiki**：把文档自动整理为 OKF 概念页的 Wiki 生成内核；
> 3. **openwiki-server（本仓库）**：上述两者的服务化封装，对外提供 HTTP / gRPC / Celery / MCP / CLI 五类能力面。
>
> **使用约定**：文中涉及 openwiki-server 引擎行为的部分，以本仓库当前实现为准；OKF 官方规范超出引擎实现的部分会明确标注「规范要求」，并以官方 SPEC 为准。

---

## 1. 背景与范围

### 1.1 业务背景

传统做法把「文档」整体扔进知识库，带来三个问题：文档太大没法按问题命中、更新后旧内容无法追溯、跨文档引用靠人工维护。OKF + OpenWiki 的思路是：

- **先切分**：把一篇长文档拆成若干「概念页」，每个概念页是一个自洽的知识单元；
- **再标注**：每个概念页通过 front matter 记录自己的元数据（标题、类型、标签、来源、状态）；
- **再互链**：概念页之间用标准 Markdown 链接形成知识网；
- **最后检索**：基于概念页提供树、搜索、统计等消费能力。

### 1.2 三个来源的关系

| 层 | 是什么 | 在本仓库中的角色 |
| --- | --- | --- |
| Google OKF v0.2 | 开放知识格式规范（数据契约） | 概念文件的目录结构、front matter、生命周期、溯源字段的“标准答案” |
| LangChain OpenWiki | Node.js Wiki 生成内核（CLI） | 把业务文档经 LLM 整理为 OKF 概念包（`.openwiki/wiki` 目录） |
| openwiki-server | Python 服务（本仓库） | 内核调用、OKF 解析、规则降级、增量合并/废弃、持久化与对外接口 |

### 1.3 本文档范围

- 概念与术语（第 2 章）；
- 知识包目录与概念文件书写规范（第 3 章）；
- 建库与切页业务规则（第 4 章）；
- 页面生命周期、可信度与溯源（第 5 章）；
- 构建、合并、废弃与异步任务流程（第 6 章）；
- 查询与展示语义（第 7 章）；
- 附录：系统字段总表、端到端示例、接口能力面、参考资料（第 8 章）。

---

## 2. 核心术语与概念映射

### 2.1 业务术语

| 术语 | 业务含义 | 备注 |
| --- | --- | --- |
| 知识库 KB（kbId） | 业务侧的知识容器，如「产品手册库」 | 创建 Wiki 实例时必填 |
| Wiki 实例（wikiId） | 知识库在引擎中的实例，一个 KB 对应一个 Wiki | 有独立配置（wikiConfig）与独立存储 |
| 源文档 Doc（docId） | 业务输入的一篇原始文档 | 支持标题、标签、Markdown 正文 |
| 知识单元 Concept | OKF 里一个可独立引用、检索的最小知识块 | 文件形态：一个 `.md` 概念文件 |
| 页面 Page（pageId） | Concept 在引擎中的落库形态 | 带 level、父子关系、字段、链接、来源 |
| 稳定键 stableKey | 页面在同一知识库内的稳定标识 | 由标题规范化而来，决定是否“同名合并” |
| front matter | Markdown 文件开头的 `---` 元数据块 | 记录 type/title/tags/sources/status 等 |
| 概念链接 | 概念页之间的引用（`[[标题]]` 或 `[文字](x.md)`） | 形成知识网 |
| 来源追溯 sourceDocs | 页面由哪些源文档产生 | 决定增量废弃时能否安全下线 |

### 2.2 OKF 概念 → 引擎落地映射

| OKF v0.2 | openwiki-server 落地 | 说明 |
| --- | --- | --- |
| Knowledge Bundle（目录树） | Wiki 实例的 OKF 包目录 `.openwiki/wiki/` | 同一份“目录即知识包”的形态 |
| Concept（一个 `.md`） | 一条 Page 记录 | 入库前解析为稳定 ID + 字段 + 正文 |
| Concept ID（相对路径去 `.md`） | stableKey + pageId | 引擎用 `kbId:stableKey` 派生稳定页面 ID |
| `index.md` / `log.md`（保留文件） | 解析时跳过，不生成页面 | 任意目录层级都保留 |
| front matter | tags / fields / status / sourceDocs | 系统键特殊处理，业务扩展键进入 fields |
| Source / Provenance | sourceDocs 列表 | 每个页面记录“由哪些 doc 产生” |
| Link | links 列表（title + pageId） | 正文里的双向/单向引用被解析并去重 |

> **业务要点**：OKF 世界里的“知识”最小单位不是文档、不是章节，而是**概念页**。文档是输入，概念页是产出，二者通过 `sourceDocs` 保持可追溯关系。

---

## 3. OKF 知识包目录与概念文件规范

### 3.1 知识包目录结构

一份 OKF 知识包就是一个 **Markdown 目录树**。openwiki-server 中每个 Wiki 实例的磁盘布局为：

```text
data/wikis/{wikiId}/
├── sources/              # 业务原始文档落盘区（构建时的输入）
└── .openwiki/wiki/       # OKF 概念包（内核产出或人工维护的概念 .md）
    ├── index.md          # 目录页（渐进披露入口，非概念）
    ├── log.md            # 更新历史（非概念）
    ├── xxx.md            # 概念文件
    └── sub/yyy.md        # 子目录概念文件
```

引擎解析概念包时：**任意层级**下名为 `index.md`、`log.md` 或以 `.` 开头的文件一律跳过、不生成页面；其余 `.md` 文件都是概念。

### 3.2 保留文件职责（OKF 规范要求）

| 保留文件 | 职责 | 约束 |
| --- | --- | --- |
| `index.md` | 目录 / 渐进披露（从概览逐层下钻的入口） | 不得承载概念内容 |
| `log.md` | 按时间顺序记录知识包的更新历史 | 不得承载概念内容 |

> **业务约定**：写导航与更新记录请放到 `index.md` / `log.md`；想让它成为可检索、可引用的知识单元，请写成独立概念文件。

### 3.3 概念文件（front matter + 正文）

概念文件 = front matter 元数据块 + Markdown 正文。

```markdown
---
title: 产品手册 · 安装          # 展示标题（缺省取文件名）
stableKey: 安装                 # 稳定键（缺省取文件名 stem）
type: Playbook                 # 概念类型（OKF 建议必备）
description: 安装步骤与负责人     # 描述（建议）
tags: [产品手册, 安装, 操作]      # 标签（建议；用于浏览索引）
sources:                       # 溯源：页面来自哪些文档
  - id: doc_1
    resource: 产品手册_v3.md
    title: 安装章节
status: active                 # 生命周期（见第 5 章）
负责人: 张三                    # 业务扩展键 —— 将进入页面 fields
---

# 安装

安装前确认环境变量。负责人按页面字段为准。
```

**字段分类（引擎口径）**：

| 分类 | 键 | 去向 |
| --- | --- | --- |
| 系统键（一等待遇） | `title` / `stableKey` / `type` / `tags` / `sources` / `status` / `generated` / `stale_after` | 分别进入标题、稳定键、标签、来源、状态等结构化字段；**不进入**自由 fields |
| 业务扩展键（自由字段） | `description`、`负责人`、`verified`、`extensions` 等其余任意键 | 保留进页面 `fields`，随页面一起检索、导出 |

> **规范要求（OKF）**：消费者应保留未知扩展键，不得因“不认识”而拒绝概念。引擎行为与此一致——扩展键一律保留到 `fields`。

### 3.4 正文与链接书写建议

- 正文用标准 Markdown，结构清晰优先；
- 建议用约定俗成的段落标题组织内容，例如 `# Schema`、`# Examples`、`# Computation`，便于 LLM/人工维护与切片；
- 需要“证据化”的结论，可用脚注引用 `sources[].id`，做到“观点可溯源”；
- 页面间引用写 `[[页面标题]]` 或 `[链接文字](other-page.md)`，引擎会解析为 `links`（标题 + 目标 pageId）；
- 不要对 `index.md` / `log.md` 建内容链接（它们不是概念目标）。

---

## 4. 知识管理业务规则

### 4.1 库配置 wikiConfig

创建 Wiki 实例时可传入 `wikiConfig`，控制切页、字段抽取、链接与去重行为。缺省值如下：

| 配置项 | 默认值 | 可选值 | 业务作用 |
| --- | --- | --- | --- |
| `granularity` | `auto` | `auto` / `heading` / `section` / `page` | 一篇文章拆成多细的页面 |
| `extractFields` | `[]` | 字符串数组 | 从正文抽取哪些「字段：值」为结构化字段 |
| `linkMode` | `auto` | `auto` / `off` | 是否自动解析页面链接 |
| `dedup` | `merge` | `merge` / `overwrite` / `skip` | 同名页面再次构建时如何合并 |
| `template` | `""` | 字符串 | 传给内核的提示模板（高级） |

非法取值会被拒绝并返回参数错误，业务方需先校验。

### 4.2 切页粒度 granularity

| 取值 | 业务效果 |
| --- | --- |
| `page` | 整篇文档作为 1 个一级页面，不做拆分 |
| `heading` | 按标题拆：一级标题（H1）是根页面，二级标题（H2）是挂在根页下的子页面；H3 及以下保留在所属页面正文里，不单独建页 |
| `section` | 以“章节树”为目标组织页面；当前引擎实现与 `heading` 等价，保留枚举以兼容后续“章节聚合”语义 |
| `auto` | **默认**。文档里有 H1/H2 标题则按标题拆（同 `heading`）；完全没有标题则整篇作单页 |

### 4.3 稳定 ID 与同名合并

引擎用稳定算法保证“同一知识单元在不同批次构建中拿到同一个 ID”，这是增量更新的地基。

- **标题规范化**：去掉所有非文字数字字符与下划线、转小写；结果为空时记为 `untitled`。
- **库级 ID**：`wikiId = "wiki_" + sha1(kbId)[前12位]`
- **页面 ID**：`pageId = "wiki_" + sha1(kbId + ":" + stableKey)[前12位]`

示例（`kb_demo` 库）：

| kbId / stableKey | 派生结果 |
| --- | --- |
| `kb_demo` | `wiki_fb42912a4348` |
| `kb_demo` + `产品手册` | `wiki_6b5b2f362211` |
| `kb_demo` + `安装` | `wiki_db59de0a98b0` |
| `kb_demo` + `安装说明` | `wiki_08aaf62d8e12` |

> **业务要点**：标题“安装”与“安装说明”会产生不同 stableKey 与 pageId，是两页；而“安装 / 安装说明 / 安装(旧版)”这类噪声会被规范化规则处理后趋同，同名即触发合并语义（见 4.6）。

### 4.4 字段抽取 extractFields

规则切页模式下，引擎只在正文中匹配形如 `键：值`（支持中文键与 `\w+`）的行，且**键必须命中 `extractFields` 白名单**才会进入结构化 `fields`：

```markdown
安装说明。负责人：张三
```

当 `extractFields = ["负责人"]` 时，页面得到 `fields: {"负责人": "张三"}`；白名单外的 `键：值` 行不会被抽取。

OpenWiki 内核模式则直接读概念文件 front matter：系统键之外的扩展键都会进入 `fields`，与白名单等效的键（如 `负责人`）即成为结构化字段。

### 4.5 链接模式 linkMode

| 取值 | 业务效果 |
| --- | --- |
| `auto` | **默认**。自动解析正文中的 `[[标题]]` 与 `[文字](xxx.md)`，生成页面 `links`（标题去重、按标题排序、目标指向其稳定 ID）；`index.md`/`log.md` 不作为链接目标 |
| `off` | 不自动解析链接（规则模式下关闭抽链；正文原文不变） |

OpenWiki 内核产出的概念页互链由内核生成，入库解析时同样会识别 `[[...]]` 与 `.md` 链接。

### 4.6 同名页面去重 dedup

同一个 stableKey 再次构建时，按 `dedup` 决定新老内容如何合并：

| 取值 | 业务效果 | 适用场景 |
| --- | --- | --- |
| `merge`（默认） | 保留老页面的 pageId 与创建时间；标签取并集；链接按标题去重、同名后者覆盖；字段后者覆盖前者；来源文档取并集 | 多文档反复沉淀同一个概念，逐步补全 |
| `overwrite` | 保留老页面 pageId 与创建时间，其余全部用新内容替换 | 以最新文档为准 |
| `skip` | 老页面存在则完全不更新 | 只读/人工锁定页面 |

---

## 5. 生命周期、可信度与溯源

### 5.1 官方 OKF 生命周期

OKF v0.2 规定概念生命周期为 `draft`（草稿）/ `stable`（稳定）/ `deprecated`（已废弃），**缺省为 `stable`**；另支持 `stale_after`（绝对过期时刻），`now >= stale_after` 即视为过期。

### 5.2 引擎状态模型与映射

引擎当前维护更精简的状态：`active` / `deprecated`，缺省 `active`。

| OKF 概念状态 | 引擎页面状态 | 说明 |
| --- | --- | --- |
| `draft` | `active` | 草稿在引擎内可用、可检索（引擎不区分草稿与正式） |
| `stable`（含缺省） | `active` | 稳定内容，正常参与树/搜索/导出 |
| `deprecated` | `deprecated` | 已废弃，不参与树/搜索/导出 |
| `stale_after` 过期判定 | 暂不判定 | 引擎解析概念时会读取该键，但当前不主动按时间下线页面（**引擎子集，未覆盖**） |

> **业务提示**：若业务需要“到期自动下线”，当前需在应用侧依据 `stale_after` 信息自行触发 `deprecate_doc` 或人工维护，勿依赖引擎自动处理。

### 5.3 可信度与主体标注（OKF 规范要求）

OKF 用 front matter 描述“内容是谁、何时、以何种可信度产生的”：

- **主体（actor）约定**：`agent:<生产方>/<版本>`（代理/引擎）、`human:<id>`（人）、`process:<id>`（流程）；
- **`generated`**：`{by, at}`，记录“由谁在何时生成”；
- **`verified`**：`[{by, at}, ...]`，记录人工/机器的核验动作（单条不带数组时按一条处理）；
- **可信分层**：无 `verified` → `unverified`（未核验）；仅有非人类核验 → `machine-confirmed`（机器确认）；含 `human:<id>` 核验 → `human-reviewed`（人工复核）；
- **时间戳**：ISO 8601 且带 UTC 偏移，如 `2026-06-30T14:00:00Z`。

**引擎口径（子集）**：`generated` / `stale_after` 由内核管理与产出，解析入库时不进入自由 `fields`；`verified`、`description` 等其余键原样保留进 `fields`。当前引擎不做可信分层判定，业务如需强可信流程，可基于 `fields.verified` 自行实现。

### 5.4 页面溯源与证据

每个页面维护三类证据：

| 字段 | 内容 | 业务用途 |
| --- | --- | --- |
| `sourceDocs` | 产生本页的源文档 docId 列表 | 判断“这篇文档下线会删掉哪些页面” |
| `fields` | front matter 扩展键 / 正文抽取的结构化字段 | 负责人、状态等业务属性的结构化沉淀 |
| `links` | 本页引用的概念页（title + pageId） | 概念网导航与“影响面”分析 |

---

## 6. 构建与增量更新流程

### 6.1 双通道构建

每次「按文档建页」走两条通道之一：

```text
业务文档(docId + title + tags + markdown)
        │
        ├─ 通道 A：OpenWiki 内核（LLM 合成）   ← 优先
        │    1) 原文写入 sources/{docId}.md
        │    2) 以该 Wiki 目录为 HOME 执行 openwiki personal --update
        │    3) 解析 .openwiki/wiki/ 下 OKF 概念页
        │    成功且解析出页面 → mode = "openwiki"
        │
        └─ 通道 B：规则切页（确定性、离线兜底）
             按 granularity 拆页 + extractFields 抽字段 + linkMode 抽链
             始终可用 → mode = "rule"

之后统一：按稳定 ID upsert（受 dedup 约束）→ 增量废弃旧页 → 返回结果
```

**守卫式降级**：OpenWiki 未安装、LLM 调用失败或解析不出页面时，自动回落规则通道，保证离线/无 LLM 全链路可用。业务方无需关心内核是否可用，接口返回 `mode` 字段表明本次实际走哪条通道。

### 6.2 一次构建的完整步骤

1. **校验**：核对 wikiConfig（非法即拒绝），缺省项自动补默认值；
2. **建页**：按 6.1 生成页面规格（title / stableKey / level / fields / links / sourceDocs / status）；
3. **落库**：每个页面按稳定 ID upsert，合并语义由 `dedup` 决定；
4. **增量废弃**：若本次构建指定了 docId，对该文档“独有且本次未再现”的旧页面标记 `deprecated`；
5. **返回**：`{mode, total, deprecated, pages}`，供调用方核对。

### 6.3 增量废弃规则

废弃只针对“由该源文档独家贡献、本次构建又未再次生成”的页面，具体判定：

- 页面 `sourceDocs` 含该 docId；
- 页面 stableKey 不在本次新建的 active 键集合中；
- 页面 `sourceDocs` **恰好等于** `{该 docId}`（即没有其他文档也贡献过它）。

满足以上全部条件才标记 `deprecated`；被多个文档共同贡献的页面不会被单次文档更新误杀。另有 `deprecate_doc` 接口支持业务显式废弃某个文档产出的全部页面。

### 6.4 全量刷新 / 摄取 / 异步任务

| 操作 | 含义 | 说明 |
| --- | --- | --- |
| `update` | 全量刷新知识包（OpenWiki 内核重整理） | 需内核可用，否则报错 |
| `ingest` | 连接器摄取（git-repo / web-search / notion 等） | 需内核可用 |
| `build` / `merge` / `export` 等异步任务 | 登记到任务表（pending → success/failed） | broker 不可达时保持 pending，可用 run_job 手动同步执行 |

业务侧提交长耗时操作（如带 LLM 的 build / update / ingest）建议走异步任务，凭 `jobId` 查询状态与结果。

---

## 7. 查询与展示语义

| 能力 | 返回 | 业务口径 |
| --- | --- | --- |
| `tree` | 页面树 | 只含 `active` 页面；无父页面者为根；按 `parentPageId` 挂接子页面；根节点分页 |
| `page` | 单页详情 | 完整 markdown、fields、tags、links、sourceDocs、状态与时间 |
| `search` | 命中列表 | 见下方检索规则 |
| `stat` | 统计 | 总页数、active / deprecated 数、链接总数、标签分布 |
| `export` | 机器可读导出 | 服务层支持 `jsonl`（默认，每行一个 active 页对象）与 `json`；OKF 目录包原生存在于 `.openwiki/wiki/`，可直接取用 |

**检索规则（search）**：

| 规则 | 权重/行为 |
| --- | --- |
| 命中标题 | +10 |
| 命中正文 | +3 |
| 命中链接标题 | +1 |
| 标签过滤 | 可附加 `tag`，不命中标签直接排除 |
| 排序 | 分数降序，同分按标题升序 |
| 上限 | limit 默认 20；q 为空时返回全部页面 |

命中项返回 `pageId / title / snippet / tags / score`；摘要取正文首行去掉 Markdown 符号后的前 80 字。

---

## 8. 附录

### 8.1 系统键与去向总表

| front matter 键 | 官方建议 | 引擎处理 |
| --- | --- | --- |
| `type` | 概念类型（OKF 必备） | 解析期读取（缺省 concept），不进入自由 fields |
| `title` | 展示标题 | 覆盖文件名作为页面标题 |
| `stableKey` | 稳定键 | 参与稳定页面 ID 派生 |
| `tags` | 标签（浏览索引） | 进入页面 tags |
| `sources` | 溯源列表 | 折算为 `sourceDocs`（兼容 `docId` / `doc_id` / `id` / 纯文本标量） |
| `status` | 生命周期 | 接受 active/deprecated；其余未知值归一为 active |
| `generated` | 生成记录 | 不进入自由 fields（保留于概念文件本身） |
| `stale_after` | 过期时刻 | 不进入自由 fields（当前不做自动过期判定） |
| 其余任意键 | 扩展字段，应保留 | 原样进入页面 `fields`（JSON 安全化） |

### 8.2 端到端示例（规则模式）

输入：`kbId = kb_demo`，`wikiConfig = {granularity: heading, extractFields: [负责人]}`，文档如下：

```markdown
# 产品手册

## 安装

安装说明。负责人：张三

## 升级

升级说明。负责人：李四
```

产出（`dedup` 缺省 merge）：

| 页面 | stableKey | level | parentPageId | 关键内容 |
| --- | --- | --- | --- | --- |
| 产品手册 | 产品手册 | 1 | （空，根页） | 根页面 |
| 安装 | 安装 | 2 | 产品手册页 | fields: 负责人=张三；sourceDocs: [doc_1] |
| 升级 | 升级 | 2 | 产品手册页 | fields: 负责人=李四；sourceDocs: [doc_1] |

### 8.3 五类能力面一览

- **HTTP**（FastAPI，前缀 `/api/v1/wiki`，默认端口 18011）：wikis 增删查、tree / page / search / stat / export、build / merge / deprecate-doc / update / ingest、jobs；
- **gRPC**（默认端口 50052）：`WikiService` 方法集与 HTTP 语义一一对应；
- **Celery**：`openwiki_server.build / merge / deprecate_doc / export / update / ingest`，支持 HTTP `async=true`；
- **MCP**（stdio，`openwiki-server serve mcp`）：`wiki_*` 系列工具，供 AI 客户端调用；
- **CLI**（typer，退出码 0/1/6 约定同 open-ikc `ikc`）：serve / wiki / job 子命令。

### 8.4 参考资料

- Google OKF v0.2 官方规范：`https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md`
- LangChain OpenWiki：`https://github.com/langchain-ai/openwiki`
- 本仓库设计文档：`docs/解决方案.md`、`README.md`
- 接口调用示例：`docs/命令行测试与调用指南.md`

