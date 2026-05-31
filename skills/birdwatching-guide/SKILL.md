---
name: birdwatching-guide
description: 生成离线 HTML 观鸟攻略网页。当用户要为某个地点/某次出行制作观鸟攻略、观鸟计划、观鸟行程，或问"去某地观鸟该看什么鸟/什么时候去/天气怎样/有哪些热点"，又或者想把 eBird、天气、小红书、中国观鸟记录中心的信息整合成一份可离线查看的攻略时，使用本 skill。即使用户没明说"攻略"二字，只要意图是规划一次观鸟出行并要一份整合好的成果，也应触发。
---

# 观鸟攻略生成工作流

本 skill 用「主 Agent 编排 + 4 子 Agent 并行采集」的模式，把多个数据源整合成一份**自包含的离线 HTML 观鸟攻略**。

核心理念：主 Agent 负责确认需求、调度、组装；4 个子 Agent 并行去各自数据源拉数据并**只返回摘要**（不是全量），这样主 Agent 上下文不会被原始数据撑爆。两个数据源有官方 API（稳）、两个没有（脆弱，做降级处理）。

## 触发后先做这件事：检查凭证

观鸟攻略依赖外部数据。开工前先确认 key 是否就绪——缺 key 不要假装能拿到数据，而是明确告诉用户去哪申请。

所有 key 集中在 `~/.birdwatch/config.json`（env 作回退），脚本自动读取。检查：
- **eBird**：`ebird_api_key`。缺则引导看 [references/ebird-api.md](references/ebird-api.md) 申请（2 分钟，免费）。
- **和风天气**：`qweather.*`（host/sub/kid + 本地 Ed25519 私钥），JWT 认证。缺则看 [references/qweather-api.md](references/qweather-api.md)。
- **观鸟记录中心（两条路，见 [references/birdreport.md](references/birdreport.md)）**：
  - *公开区域数据*：`birdreport_public.py`，**无需 token**（只需 Node）。用于"区域鸟况/热门点位"。
  - *个人记录/可加新比对*：`lifelist.py`，需 `birdreport.token`（缺则跑 `birdreport-logger/scripts/grab_token.py`）。
- **小红书**：无官方 API，增强源，缺失跳过。

eBird 和天气是地基，缺则先停下帮用户搞定；观鸟记录中心两条路都属增强，缺失**跳过而非报错**。

## Phase 0 · 准备（主 Agent 自己做）

1. **确认出行**：和用户对齐 3 件事——目的地、日期（或日期范围）、关注点（新手/冲特定鸟种/纯休闲）。缺了就问，别猜。
2. **地点定位**：把目的地解析成 `纬度,经度` 和 **eBird region code**（如北京=`CN-11`，或用经纬度调附近端点）。region code 查法见 [references/ebird-api.md](references/ebird-api.md)。
3. **读历史 + 个人 CSV**：如果用户提供了历史攻略文件或个人观鸟记录 CSV（哪些鸟已"解锁"），读进来——Phase 2 比对要用。没有就跳过，不影响主流程。

## Phase 1 · 四线并行采集（4 子 Agent 同时跑）

用 Agent 工具**在同一轮里并行 spawn 4 个子 Agent**（不要串行，串行就失去并行的意义）。每个子 Agent 的任务 prompt 模板见 [references/sub-agent-prompts.md](references/sub-agent-prompts.md)，照抄并填入 Phase 0 的参数即可。

| 子 Agent | 数据源 | 产出摘要 | 缺 key 时 |
|---------|-------|---------|----------|
| 🦅 eBird | 官方 API（脚本） | 附近近期观测、热点 Top5、高光/罕见鸟种 | 必需，缺则停 |
| ☀️ 天气 | 和风 API（脚本） | 3 天预报、降水概率、风向、观鸟时段建议 | 必需，缺则停 |
| 📋 观鸟记录中心 | `birdreport_public.py`（公开/front, 无token） | 区域**公开**报告数、热门点位 Top、近期鸟况（所有鸟友）| 可选，缺 Node 则跳过 |
| 🔴 小红书 | MediaCrawler | 近期帖子鸟况、出行/封控提醒、拍摄机位 | 可选，缺则跳过 |

**降级策略**：可选子 Agent 失败或超时，主 Agent 在最终 HTML 里如实标注"该板块数据暂缺"，继续组装。绝不让一个脆弱数据源拖垮整份攻略。

**为什么要子 Agent 而不是主 Agent 直接拉**：每个数据源返回的原始 JSON 很大（eBird 一个热点可能几百条观测）。子 Agent 在自己的上下文里消化，只把"高光鸟种 + 热点排名 + 关键提醒"这种攻略真正要用的结论带回来。

## Phase 2 · 组装输出（主 Agent）

1. **鸟种比对**：把 Phase 1 汇总的鸟种 vs **个人人生鸟单**比对，标记每个种是 `可加新`（没记录过，去了能加新种）还是 `已解锁`。这是攻略的"游戏化"亮点。
   - 人生鸟单优先读 `~/.birdwatch/lifelist.json`（来自中国观鸟记录中心，由 birdreport-logger 的 `lifelist.py` 生成/刷新），按鸟种**中文名**匹配。
   - 该文件不存在时，提示用户先刷新人生鸟单，或退回用户提供的 CSV；都没有就跳过标记。
2. **填 HTML 模板**：用 [assets/guide-template.html](assets/guide-template.html)，把数据填进三大可视化区块——**鸟种卡片**、**鸟况时间线**、**推荐路线/热点**。模板是自包含的（CSS 内联、无外链），保证离线可看。填充规则见模板内注释。
3. **保存 + 检查**：输出到用户指定路径（默认当前目录 `观鸟攻略_<地点>_<日期>.html`）。存完自检三点：① 文件能独立打开（无外部依赖）② 所有数据占位符都已替换（不留 `{{...}}`）③ 缺失板块有友好提示而非空白或报错。

## 飞书 / 移动端交付（经 CC-Connect bot 触发时）

当本 skill 是被**飞书 DM（经本机 CC-Connect）**触发、而非本地终端时，用户在手机上看不到本机 HTML 文件，须按移动端形态交付：

1. **聊天精简摘要**：直接在回复正文给 Markdown 要点——最佳日（天气）、必看/高光鸟种、热点 Top、本次⭐可加新种。飞书支持 Markdown/卡片，手机秒看，这是主交付。
2. **HTML 文件发进会话**：用 cc-connect 原生命令把离线 HTML 发到当前会话（它按会话上下文自动路由，无需 chat_id）：
   ```bash
   cc-connect send --file "<HTML 绝对路径>"
   ```
   `--file`/`--image` 可重复；用绝对路径最稳。前提是会话已注入 cc-connect 指令（`/bind setup` 时完成）。
3. **同时存进 vault**：把攻略另存一份 Markdown 到 `观鸟/guides/<date> <地点>.md`（鸟种用 `[[双链]]`，可加新种标 ⭐）并 `git push`——手机 Obsidian 同步可看，且并入观鸟图谱。这也是文件发送失败时的兜底。

> 判断渠道：运行环境是飞书/cc-connect 会话（无本地 GUI）时按上面三步；普通本地终端则照常只产 HTML。

## 数据获取脚本

eBird 和天气是确定性 API 调用，已封装成脚本，子 Agent 直接调用，不要每次重写：

- `scripts/ebird_fetch.py` — eBird 附近观测/热点/罕见种，详见脚本内 `--help`
- `scripts/qweather_fetch.py` — 和风 3 天预报

两个脚本都从环境变量读 key，输出精简 JSON 供子 Agent 消化。

## 参考文档索引

- [references/ebird-api.md](references/ebird-api.md) — eBird key 申请 + 端点说明 + region code 查法
- [references/qweather-api.md](references/qweather-api.md) — 和风天气 key 申请 + API host 说明
- [references/birdreport.md](references/birdreport.md) — 中国观鸟记录中心接入（社区工具，无官方 API）
- [references/xiaohongshu.md](references/xiaohongshu.md) — 小红书数据采集（MediaCrawler，注意合规风险）
- [references/sub-agent-prompts.md](references/sub-agent-prompts.md) — 4 个子 Agent 的任务 prompt 模板
