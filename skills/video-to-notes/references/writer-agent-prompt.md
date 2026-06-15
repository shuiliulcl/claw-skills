# Writer Agent Prompt 模板

调 Sonnet 4.6 子 Agent 写完整中文笔记。这是 token 大头, 必须用 Sonnet。

## 调用模板(Python style, 主线程)

```python
Agent(
    description="Write Chinese teaching notes",
    model="sonnet",  # 不要省, 默认会跟主线程模型
    subagent_type="general-purpose",
    prompt=PROMPT_TEXT.format(
        video_meta="<演讲者名 + 频道 + 主题一句话>",
        time_anchors="<章节锚点表>",
        transcript_path=r"D:\Obsidian Vault\工具\video-notes\<slug>\transcript.txt",
        figures_dir=r"D:\Obsidian Vault\工具\video-notes\<slug>\figures_full\renamed",
        figures_extra=r"D:\Obsidian Vault\工具\video-notes\<slug>\figures\renamed",  # 可选
        style_reference=r"D:\Obsidian Vault\工具\video-notes\<prev-slug>\notes_full.md",  # 可选
        output_path=r"D:\Obsidian Vault\工具\video-notes\<slug>\notes_full.md",
    ),
)
```

## PROMPT_TEXT(直接复用)

```
你的任务: 把一段 {video_length} 的英文技术演讲字幕 + 抽出来的关键帧, 转写成一份**高可读性、信息高度保留的中文图文笔记**(Markdown).

## 上下文

视频: {video_meta}

## 已有风格基准(若提供)

{style_reference} — 已经过用户确认的风格范例. 必须延续:
- 教学叙事口吻(动机 → 核心思路 → 机制 → 示例 → 取舍), 不按时间顺序流水账
- 主语是"概念/技术"而不是"演讲者", 除非确实要交代来源
- 中文为主, 技术术语保留英文
- 数字 / API 名 / 工具名 / 性能数据全保留
- 配图按"实质帮助"标准, 不凑数; 每张配 caption 含 "来源 HH:MM:SS"
- 不用 emoji 标题, 不用代码块装饰非代码
- 关键 benchmark 表用 markdown 表格复刻数值

**⚠️ 关键: 风格基准只用来参考排版、措辞、章节组织, 不要拷贝事实内容**

风格基准是**别的视频**的笔记. 以下信息**必须**从本次的 {transcript_path} 重新提取, **绝不能**沿用基准里的值:
- 视频 URL (callout 里那条 youtu.be 链接)
- 发布日期
- 时长(HH:MM:SS)
- 演讲者姓名(包括正确拼写, 不要"差不多")
- 频道 / 节目名 / 主办方
- 任何具体的数字、API 名、产品名

历史上踩过的坑: writer 把上一篇笔记的 URL / 日期 / 演讲者名都抄过来了, 用户一眼就发现. 写 callout 和 blockquote 这两块**专门停下来核对一遍 transcript 第一段的开场介绍**, 不要凭印象写.

如未提供风格基准, 按上述要求自己执行.

## 视频结构(章节锚点)

{time_anchors}

例:
| 时间区间 | 内容 |
|---|---|
| 04:44 - 09:00 | 主持人 + 嘉宾介绍 + 主题背景 |
| 09:00 - 15:50 | Method 1: Spawned Actor |
| ... | ... |

## 输出文档结构

最终 markdown **必须**按以下顺序:

```markdown
---
title: <中文翻译标题, 跟用户在飞书设置的页面标题一致>
title_en: <原视频英文标题完整, 包含 | Inside Unreal 等后缀>
aliases: [<别名列表, 便于搜索, 比如方法名/概念名/演讲者别名>]
tags: [ue5, <主题如 gameplay/animation/rendering>, <子主题>]
category: video-notes
created: YYYY-MM-DD  # 第一次写笔记的日期
updated: YYYY-MM-DD  # 当次写作日期
video_url: <youtu.be 短链或完整 URL>
duration: <1hXXmXXs>
speaker: <演讲者姓名, 多个用逗号>
channel: <Inside Unreal / GDC / Unreal Fest 等>
publish_date: YYYY-MM-DD  # 视频发布日期
sources:
  - transcript: D:/Obsidian Vault/工具/video-notes/<slug>/transcript.txt
  - github: <若演讲附 GitHub 项目>
feishu_wiki: <若已发布到飞书, 留位用户填; 第一次写为空字符串>
---

<callout>... 视频 URL + 元信息 ...</callout>
> 演讲者背景 blockquote
## 第一个 H2 章节
...
## ... 各章节 ...
## Q&A 技术精华
## Related Concepts
- [[<其它笔记的相对路径>|<显示名>]] — 一句话说明关联点 (动机/对照/前置/后续)
- [[<另一个>|<显示名>]] — ...
> 收尾(尾部 blockquote, 列 GitHub / 关键资源)
```

### Related Concepts 章节(可选, 宁缺毋滥)

**Related Concepts 是宁缺毋滥的可选章节**: 如果给了 `style_reference` (上一篇笔记), 你**可以**思考两份笔记是否真的有关联。**判断标准是严苛的**:

- 关联点必须**一句话能说清** — 如果你需要解释三句才能让读者觉得"哦确实相关", 这就是牵强, 不要写
- 主题差异大的两份笔记(比如"摄像机系统" vs "子弹处理") **大概率没有真关联**, 哪怕都是 UE5。"都用了 GameplayTag" 这种 UE5 通用模式不算关联点 — 那是几乎所有 UE5 系统的共性, 写出来等于没写
- "Benchmark 互为佐证" / "类似设计哲学" / "同一思路" 这种抽象表述, 99% 的情况下是在硬掰
- **历史踩坑**: BlackEye 笔记里我曾把"摄像机不是组件" vs "Pooled Actor 不重复 spawn"、"Gameplay Modifiers" vs "Multi-Trace handler 中央数组"、"Trigger Volume + tag" vs "Pool event subscription" 凑成三条 Related Concepts。用户反馈"牵强", 全部删掉了。**关注点不同就是不同, 不要为了"格式完整"凑数**

**正确判断流程**:

1. 读完 style_reference, 列出该笔记的核心主题(比如 "Pooled Actor 性能优化")
2. 读完本次 transcript, 列出本笔记的核心主题(比如 "摄像机构图与运动学")
3. 问自己:**两个核心主题之间, 真有读者会觉得"哦这两个一起看更清楚"的关系吗?**
4. 如果有, 一条简短的 link + 一句话说明为什么。
5. 如果没有, **省略整个 Related Concepts 章节**。一条牵强的关联比 0 条更糟, 会拉低整篇可信度。

如果决定写, 必须用 Obsidian wikilinks: `[[ue-camera-blackeye/notes_full|Black Eye 2.0]]` (不要用 markdown URL)。理由: Obsidian 原稿要让双向链 / graph view 工作; 转飞书时 `scripts/to_feishu.py` 会通过 registry 自动翻译。

1. **完整字幕**: {transcript_path}
   - 干净, 已去重, 每行 `[HH:MM:SS] 文本` 格式
   - 自动 CC, 数字 / API 名 / 术语偶有拼错, 上下文判断
2. **候选关键帧**: {figures_dir}
   - 命名 `slide_HH-MM-SS.jpg`, 全部 720p, 已用绝对时间戳
3. **额外可用帧**(可选): {figures_extra}

## 工作流

1. 先 Read 风格基准文档(若有), 完整把握风格
2. Read 完整 transcript, 在脑里建结构, 找出每个 method/section 的起止时间
3. Read **每张候选帧**, 给每张做一句话定性 — slide / demo 镜头 / talking head / Blueprint 截图 / benchmark 表
   - 对 talking head 镜头一律弃用, 它们是无信息背景
   - 对画面与已选图重复的 demo 镜头(同场景同角色)挑一张代表
4. 决定每章节用哪些图, 按"实质帮助"标准选(不要凑 13 张)
5. 写出完整 Markdown
6. Write 到 {output_path}
7. 在最终消息回复:
   - 输出文件路径 + 字节数
   - 按章节列出实际用了哪些图(时间戳 + 一句话用途)
   - 哪些图明确丢弃, 简单理由
   - **章节图覆盖自检**: 列出所有 H2 章节, 标注每个章节图片数量。对 0 图但**本应有图**的章节(专属 UI / Panel / 工具截图 / Sequencer / 节点编辑器 / Blueprint 截图 / benchmark 表 / 对话场景 / 复杂构图演示), 即使候选池里没合适的图, 也明确写出"建议补图: <章节名>, 候选区间 HH:MM-HH:MM, 关键词 <keywords>" — 主线程会基于此定向补抽
   - **你转写中把握不大的技术细节**(数字 / API 名拼错 / 听不清), 标出最佳猜测
   - **你主动延展或合并**的章节(比如 Q&A 怎么压缩的)

## 关键约束

- 不要在最终消息里复述整篇 markdown, 我会直接读文件
- 保留风格基准已批准的措辞, 除非发现明显事实错误才微调
- Q&A 部分**只挑技术精华**, 不要逐个问答记录; 按主题聚合, 每条 3-6 行
- 最长的方法/章节给足篇幅, 配合关键 benchmark 数字
- 如果有完整对比表(比如多方法 benchmark), **把所有行都从 transcript 里挖出填齐**, 不要留 "—"

## 配图 caption 格式

每张图下面紧跟一行斜体小字 caption, 包含一句话描述 + "来源 HH:MM:SS":

```markdown
![alt 简短描述](figures_full/renamed/slide_00-14-00.jpg)
*Benchmark 表 — 6 种方法对比 · 来源 00:14:00*
```

如果是关键 benchmark 截图, **图旁边也用 markdown 表格复刻数值**, 因为字幕没有完整表内容时就靠这张, 字小可能不可读, 表是兜底.
```
```

## 调用之前主线程要做的准备

- 字幕已清洗(`scripts/clean_vtt.py` 输出 `transcript.txt`)
- 关键帧已抽并去重(`scripts/extract_keyframes.py` 输出 `figures_full/renamed/`)
- 章节锚点已用 grep 找出来(主线程的 grep 字幕找方法/章节)
- 视频元信息一句话总结(主讲、频道、主题)

## Reviewer Pass (主线程做, 便宜)

writer 输出后, **不要**再起一个 reviewer 子 Agent — 太贵且重复。主线程直接做:

1. 用 writer 标注的"把握不大"项, 在 transcript.txt 用 grep 反查
2. 抽 5-10 个**具体技术点**(数字 / 易错 API 名)做对照
3. 主线程发现遗漏就 Edit 修正, 一般 2-5 处

## 成本预算

| 项 | 单次 |
|---|---|
| Writer subagent (Sonnet 4.6) | ~110-150K |
| 主线程 grep + Edit (Opus) | ~15K |
| 总计 | 约 200K, 折算 ~30K Opus 等价 |

对比: 直接用 Opus 写, ~150K Opus, **5 倍成本**。
