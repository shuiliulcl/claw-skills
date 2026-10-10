# Writer Agent Prompt 模板

调 Sonnet 子 Agent 写完整中文笔记。这是 token 大头 (~110-150K Sonnet),必须用 Sonnet 不要用 Opus。

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

**⚠️ 风格基准只参考排版、措辞、章节组织, 不要拷贝事实内容**

风格基准是**别的视频**的笔记. 以下字段**必须**从本次 {transcript_path} 重新提取, 绝不能沿用基准:
- 视频 URL、发布日期、时长、演讲者姓名(拼写)、频道、所有具体数字 / API 名 / 产品名

callout 和开场 blockquote 这两块**专门停下来核对一遍 transcript 第一段**, 不要凭印象写.

**人名拼写坑** ⚠️ — YouTube auto-CC 对不常见姓氏拼错是常态:
- 同一人在字幕里出现多个拼法 (例: "Matt Oztalay" @10:27 vs "Matt Ostelays" @22:05) → 大概率是**同一人**, 不是两个人. 挑一个最合理的 (字幕靠后的通常更准), 不要留两个
- 演讲者提到"隔壁那场演讲"时, 常常两场**同一 author**. 主线程 reviewer 会外网核对, 你别自作主张判断
- 踩坑: Camille K "Project Health" 笔记 writer 把 "Rethinking Performance Paradigms" 归给 "Matt O'Sullivan" (auto-CC 幻觉), 实为 **Matt Oztalay** 做的三场演讲里的另一场. Reviewer 外网验证才发现

如未提供风格基准, 按上述要求自己执行.

## 视频结构(章节锚点)

{time_anchors}

例:
| 时间区间 | 内容 |
|---|---|
| 04:44 - 09:00 | 主持人 + 嘉宾介绍 |
| 09:00 - 15:50 | Method 1: Spawned Actor |
| ... | ... |

## 输出文档结构

```markdown
---
title: <中文翻译标题, 跟用户在飞书设置的页面标题一致>
title_en: <原视频英文标题完整, 包含 | Inside Unreal 等后缀>
aliases: [<别名列表: 方法名 / 概念名 / 演讲者别名>]
tags: [ue5, <主题>, <子主题>]
category: video-notes
created: YYYY-MM-DD  # 第一次写笔记日期
updated: YYYY-MM-DD  # 本次写作日期
video_url: <youtu.be 短链或完整 URL>
duration: <1hXXmXXs>
speaker: <演讲者姓名, 多个用逗号>
channel: <Inside Unreal / GDC / Unreal Fest 等>
publish_date: YYYY-MM-DD  # 视频发布日期
sources:
  - transcript: D:/Obsidian Vault/工具/video-notes/<slug>/transcript.txt
  - github: <若演讲附 GitHub 项目>
feishu_wiki: ""  # 第一次写为空字符串, 发布后由主线程填
---

<callout>... 视频 URL + 元信息 ...</callout>
> 演讲者背景 blockquote
## 各 H2 章节(主题组织,不按时间)
## Q&A 技术精华(如字幕末尾有问答)
## Related Concepts(可选, 宁缺毋滥)
> 收尾 blockquote
```

### Related Concepts 章节(可选, 宁缺毋滥)

如果给了 `style_reference`, 判断两份笔记是否真的有关联。**判断标准严苛**:

- 关联点必须**一句话能说清** — 需要三句才能让读者觉得"哦确实相关"就是牵强, 不要写
- "都用 GameplayTag" / "类似设计哲学" / "同一思路" 99% 是硬掰. 主题差异大的两份笔记大概率没真关联, 哪怕都是 UE5
- 踩坑: BlackEye 笔记里曾把"摄像机不是组件" vs "Pooled Actor 不重复 spawn" 等三条凑成 Related Concepts, 用户反馈"牵强"全删

正确流程:
1. 读完 style_reference 和本次 transcript, 各列核心主题
2. 问:**两个主题之间, 读者真会觉得"一起看更清楚"吗?**
3. 有 → 一条简短 link + 一句话说明;**无 → 省略整个章节**。一条牵强关联比 0 条更糟

决定写就用 Obsidian wikilinks: `[[ue-camera-blackeye/notes_full|Black Eye 2.0]]` — 不要 markdown URL。转飞书时 `scripts/to_feishu.py` 自动翻译。

## 输入

1. **完整字幕**: {transcript_path} — 每行 `[HH:MM:SS] 文本`, auto-CC 术语偶有拼错
2. **候选关键帧**: {figures_dir} — `slide_HH-MM-SS.jpg`, 720p 或 1080p, 绝对时间戳
3. **候选帧打分** (若存在): `{figures_dir}/../frame_quality.json`
   - `advisory` 字段: `low_info` / `talking_head` = 价值低, **跳过 Read**
   - `category`: `dead` 已剔; `code_dense` / `demo_footage` 优先 Read; `sparse` 每章节最多一张; `talking_head` 跳过
   - `similar_to`: 近似帧列表, 从每组挑一张代表(通常最后一张, slide 展开最完整)

## 工作流

1. Read 风格基准(若有), 把握风格
2. Read 完整 transcript, 建结构
3. 看 frame_quality.json 一次, 按 advisory 分 A / B / C 档, 决定要 Read 的帧集合
4. **串行 Read 关键帧**, 一次 1-2 张, 中间穿插判断。目标**总 Read 10-25 张**, 不要试图全部读完
5. **立即 Write 到 {output_path}** —— 见下方"反 API stall 硬规则", 这一步最容易出事
6. 最终消息(**简短**, 不复述正文):
   - 文件路径 + 字节数
   - 按章节列实际用了哪些图(时间戳 + 一句话用途)
   - **章节图覆盖自检**: 列出所有 H2 章节图片数量。对**本应有图但 0 图**的章节(专属 UI / Panel / Blueprint / benchmark 表 / Sequencer 等), 写"建议补图: <章节>, 候选区间 HH:MM-HH:MM, 关键词 X" — 主线程基于此定向补抽
   - 把握不大的技术细节(数字 / API 名 / 听不清的), 标出最佳猜测
   - 需要主线程查链接的外部引用
   - **`gif_candidates`(可选)**: 判定权在主线程, 你**只在读 transcript 时明显感到某段是强 GIF 候选**(物理反馈 / 玩家操作 / UI 参数拖动等强动作 demo), 才补充。找不到就不输出
     - 格式: `{time_range: HH:MM:SS-HH:MM:SS, target_caption: <静态图 caption 20-30 字片段,不含反引号>, why: <一句话>, suggested_caption: <GIF caption>}`

## ⚠️ 反 API stall 硬规则(违反就会卡死)

这几项**是硬规则不是建议**, 之前每篇长笔记都因此栽过:

### 规则 1 — 读图串行

Read 图片一次开 6-8 个并行 → API 卡断. **每次 Read 1-2 张**, 中间穿插判断文字。总 Read 控制在 10-25 张,不要贪多 —— 每张 base64 图 ~20-40K token,10 张就把 context 推到 200K+。

### 规则 2 — Read 完图之后,**同一 turn 内立即发 Write**

**不要**用一条文字消息"收尾",比如:
- ❌ "关键帧都看完了,现在整理结构,写笔记"
- ❌ "图读完了,下一步开始写"
- ❌ 任何只是"宣告下一步"的 text 块

这种 text 块会让 turn 以 end_turn 正常结束 → 任务被 harness 当作"完成了"返回主线程 → 主线程看到的最后一句就是这个状态文字 → 它以为你卡住了,又发一轮 continue, 你又进 thinking 再预演一遍,**又没真 Write**。这不是 API stall,是你自己把 turn 结束了。

正确做法: Read 完最后一张图,**不出 text**(或只出一句 ≤ 20 字的过渡),**同一个 assistant 消息里直接接 Write 工具调用**。

**同样,不要在读完图之后用超长 thinking 块"预演正文大纲"再 Write**。预演会把生成压力推到后面,反而更容易 stall。该写就写,结构在读 transcript 时就应该定下来了,不需要再在 thinking 里重排一次。

### 规则 3 — Write 单次 ≤ 12KB,>12KB 必须分片

一次 Write **≥ 15KB** 的 markdown 在 150K+ context 下 → API 卡断在流中段,从外部看就是"agent 返回同一句话,tool_uses 不涨"。实测本次 2XKO 笔记 writer 在 ~130K context 下尝试一次 Write ~17KB 直接 stall 掉。

硬规则:
- **预估正文 >12KB 时, 主动分 2 片**:
  - 第 1 次 Write: frontmatter + callout + 前半 H2 (~8-10KB), 停在某个 H2 结束处。写完回复**一句话** "前半已 Write,等继续指令" 结束 turn
  - 等主线程 SendMessage 后, 用 Edit 或再 Write 补齐后半 + Related Concepts + 收尾
- 判断不了大小就**保守分片**
- **Write 失败后部分生成的文本会丢失**,分片是唯一救回办法
- 粗估公式: `正文 KB ≈ H2 数 × 1.2 + 图片数 × 0.3 + 2`。超过 12 就分片

### 规则 4 — Caption 时间戳必须冒号

配图 caption 里"来源 HH:MM:SS"必须**全用冒号**,不要 "来源 00:16-16" 这种连字符。后者让飞书 media-insert 找不到锚点,图片静默漏插。(`to_feishu.py` 现在会自动修,但源头写对省事。)

## 内容质量原则(宁缺毋滥)

笔记里**每一句话都要给读者带价值**。以下几类"硬凑"内容必须避免:

### 引用外部演讲 / 资源必须连同链接

演讲者口头提到另一场演讲、工具、GitHub 项目、博客等**可索引外部资源**, 要引用就**必须附 URL**。**找不到链接就不要引用** — 给一个名字让读者自己搜没意义。

搜不到就在最终消息列为"主线程待查",不要塞 "可能是..." 的猜测 URL。

### 引用外部链接时必须核对版本/状态匹配 ⚠️

演讲者常区分"基础版本(已公开)" vs "演讲展示的扩展版本(未公开/即将发布)"。

- 对照 transcript **演讲者本人对资源的描述**,核对外网拿到的状态
- 如果演讲者说"stand by for next release" / "not public yet",**不能**把同名外网资源当成"演讲展示的就是这个"
- 不确定就写"演讲未给出公开下载链接",不要硬塞 URL

踩坑: StateTree 笔记第一版引用 [Project Titan Fab listing](https://www.fab.com/listings/c05aac82-4c1a-4e42-96b3-be668dc40fca) 时写"完整 StateTree 配置随样本一起开放" — 但 Sebastian [00:13:44] 明确说"next Titan release coming in a couple of months",当时 Fab 上是 2024 art jam 版,**不含**演讲展示的工具集,引用变成误导。

### 不写"纠错过程"

字幕 auto-CC 听错人名 / 术语,主线程会反查。笔记里**直接写正确的拼写**,不写"(原字幕误识别为 X,实际是 Y)" / "(auto-CC 听成 Z)"。笔记是成品,不是 changelog。

### 不写"没有 X" / "未找到 Y"

笔记里不要塞纯否定句:
- ❌ "演讲中没有公开 GitHub 仓库或示例项目下载链接"
- ❌ "X 的链接由演讲者口头提及, 但未在视频描述中附出"
- ❌ "本文档不涉及 Y / 演讲中未涉及 Z"

读者关心"有什么",不是"作者找了什么但没找到"。直接省略整段。

例外: "没有 X" 是设计决策本身(例: "该方法刻意不使用 GameplayTag,因为 ..."),属正向陈述,保留。

## 配图 caption 格式

每张图下面紧跟一行斜体小字 caption,包含一句话描述 + "来源 HH:MM:SS":

![alt 简短描述](figures_full/renamed/slide_00-14-00.jpg)
*Benchmark 表 — 6 种方法对比 · 来源 00:14:00*

如果是**关键 benchmark 截图**, 图旁边**同时用 markdown 表格复刻数值** — 字幕没给完整表时就靠这张,字小可能不可读,表是兜底。

## 其他约束

- 不要在最终消息里复述整篇 markdown, 主线程会直接读文件
- Q&A 部分**只挑技术精华**, 不逐个问答记录; 按主题聚合, 每条 3-6 行
- 完整对比表(多方法 benchmark)**把所有行都从 transcript 填齐**, 不留 "—"
```
