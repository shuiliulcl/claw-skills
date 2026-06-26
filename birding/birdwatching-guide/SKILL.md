---
name: birdwatching-guide
description: 生成离线 HTML 观鸟攻略网页，并能在用户没指定地点时智能推荐去哪观鸟。当用户要为某地/某次出行制作观鸟攻略、观鸟计划，或问"去某地该看什么鸟/什么时候去/天气怎样/有哪些热点"，或问"这周末去哪观鸟好/推荐个观鸟点/哪里能加新种"（按可加新种+鸟种丰富度+距离成本平衡推荐目标），又或想把 eBird、天气、小红书、中国观鸟记录中心信息整合成可离线攻略时，使用本 skill。即使没明说"攻略"二字，只要意图是规划观鸟出行或选目的地，也应触发。
---

# 观鸟攻略生成工作流

本 skill 用「主 Agent 编排 + 4 子 Agent 并行采集」的模式，把多个数据源整合成一份**自包含的离线 HTML 观鸟攻略**。

核心理念：主 Agent 负责确认需求、调度、组装；4 个子 Agent 并行去各自数据源拉数据并**只返回摘要**（不是全量），这样主 Agent 上下文不会被原始数据撑爆。两个数据源有官方 API（稳）、两个没有（脆弱，做降级处理）。

## 触发后先做这件事：检查凭证

观鸟攻略依赖外部数据。开工前先确认 key 是否就绪——缺 key 不要假装能拿到数据，而是明确告诉用户去哪申请。

所有 key 集中在 `~/.birdwatch/config.json`（env 作回退），脚本自动读取。检查：
- **eBird**：`ebird_api_key`。缺则引导看 [references/ebird-api.md](references/ebird-api.md) 申请（2 分钟，免费）。
- **和风天气**：配置已迁到独立 skill [weather-forecast](../weather-forecast/SKILL.md)（`~/.qweather/config.json`）。本 skill 子进程调用 weather-forecast 的 `qweather_fetch.py` 拿 3 天预报，再本地附加 `birdingHint` 字段。缺配置去那边按 [references/qweather-api.md](../weather-forecast/references/qweather-api.md) 跑通。
- **观鸟记录中心（两条路，见 [references/birdreport.md](references/birdreport.md)）**：
  - *公开区域数据*：`birdreport_public.py`，**无需 token**（只需 Node）。用于"区域鸟况/热门点位"。
  - *个人记录/可加新比对*：`lifelist.py`，需 `birdreport.token`（缺则跑 `birdreport-logger/scripts/grab_token.py`）。
- **小红书**：无官方 API，增强源。经 `xhs_search.py`（封装 MediaCrawler，需本人扫码登录）抓公开笔记。`xiaohongshu.enabled` **默认 false**；启用见 [references/xiaohongshu.md](references/xiaohongshu.md)（⚠️ xhshow 必须 0.1.9）。缺失/未启用则跳过。
- **目标推荐（Phase 0.5）**：`home_base`（大本营出发点）+ `amap.key`（高德 Web 服务，算真实驾车距离/费用）。仅在"帮用户选去哪"时需要；缺 amap.key 退化为直线距离，缺 home_base 则让用户直接指定地点。

eBird 和天气是地基，缺则先停下帮用户搞定；观鸟记录中心两条路都属增强，缺失**跳过而非报错**。

## Phase 0 · 准备（主 Agent 自己做）

1. **确认出行**：和用户对齐 3 件事——目的地、日期（或日期范围）、关注点（新手/冲特定鸟种/纯休闲）。缺了就问，别猜。
2. **地点定位**：把目的地解析成 `纬度,经度` 和 **eBird region code**（如北京=`CN-11`，或用经纬度调附近端点）。region code 查法见 [references/ebird-api.md](references/ebird-api.md)。
3. **读历史 + 个人 CSV**：如果用户提供了历史攻略文件或个人观鸟记录 CSV（哪些鸟已"解锁"），读进来——Phase 2 比对要用。没有就跳过，不影响主流程。

## Phase 0.5 · 目标推荐（用户没指定地点 / 问"去哪观鸟好"时）

当用户**没明确目的地**，或问"这周末去哪观鸟好/推荐个点"时，先帮他选目标：

```
python scripts/target_select.py [--radius 60] [--top 5]
```
它从配置的**大本营**（`~/.birdwatch/config.json` 的 `home_base`）出发，拉附近 eBird 热点，按
**平衡打分【可加新种 0.4 × 鸟种丰富度 0.25 × 就近(高德驾车时长) 0.35】**排序，输出 Top N（名称/距离/驾车时长/估算费用/可加新种数与示例/累计种数）。

- 把 Top 3–5 连同**理由**（能加哪些新种、多远多少钱）呈现给用户，让他**选一个**。
- 用户选定后，把该点作为目的地，进入下面的 Phase 1/2 出完整攻略。
- 依赖：`home_base` + `amap.key`（高德 Web 服务，算真实驾车距离/费用；缺则退化为直线距离）。缺 `home_base` 就回到"请用户指定地点"。

### Phase 0.5b · 菜鸟聚集地（"想拍某只我没加的常见鸟，去哪最容易"）

另一种选目标视角：不是"选个点看啥"，而是以**我还没加新的常见鸟**为主语，反查它**报告最集中**的点。这是观鸟"打鸟"逻辑——拍某只菜鸟最好的办法是去它高频聚集地。

```
python scripts/species_hotspots.py --month <目标月> [--years 2] [--regions 上海市/上海市,江苏省/苏州市,浙江省/嘉兴市] [--scan 6]
```
机制：取地区**目标月**（最近 N 年同月，对齐季节、避免冬鸟夏查）公开鸟种 → 减人生鸟单=可加新 → 对报告数靠前者聚合 `point_name`，用大盘基线算 **lift**（该点对该种的特异度，剔除"超级点哪都人多"的观察者效应），按 `lift × 报告量 × 拍摄难度` 排序。输出每个可加新种的最佳聚集点 + lift + 分布。

呈现给用户时：`lift>1.5` 才算该点对某种有明显偏好；带 `难拍` 标签的（杜鹃/苇鳽等闻声难见）已按习性降权，提示"好拍优先看不带难拍标签的"。

⚠️ **善待平台（强约束）**：这是 birdreport 重查询，**务必低频**——
- `--scan` 控到个位数；**结果自动缓存** `~/.birdwatch/species_points_cache.json`，再查这些种零请求；靠多次小批攒满，**绝不一次猛扫**。
- 限流(505) **直接跳过、绝不 sleep 重试**（重试放大请求量会触发持续封禁）。脚本已内置 5s 间隔。
- 接口约束同公开数据：`limit≤50`；月份用 `startTime/endTime` 日期范围（不用 `taxon_month`）。

## Phase 1 · 四线并行采集（4 子 Agent 同时跑）

用 Agent 工具**在同一轮里并行 spawn 4 个子 Agent**（不要串行，串行就失去并行的意义）。每个子 Agent 的任务 prompt 模板见 [references/sub-agent-prompts.md](references/sub-agent-prompts.md)，照抄并填入 Phase 0 的参数即可。

| 子 Agent | 数据源 | 产出摘要 | 缺 key 时 |
|---------|-------|---------|----------|
| 🦅 eBird | 官方 API（脚本） | 附近近期观测、热点 Top5、高光/罕见鸟种 | 必需，缺则停 |
| ☀️ 天气 | weather-forecast skill / 和风 API | 3 天预报、降水概率、风向、观鸟时段建议 | 必需，缺则停 |
| 📋 观鸟记录中心 | `birdreport_public.py`（公开/front, 无token） | 区域**公开**报告数、热门点位 Top、近期鸟况（所有鸟友）| 可选，缺 Node 则跳过 |
| 🔴 小红书 | `xhs_search.py`(MediaCrawler 封装) | 近期帖子鸟况、微点位/机位、出行提醒 | 可选(默认关)，缺则跳过 |

**降级策略**：可选子 Agent 失败或超时，主 Agent 在最终 HTML 里如实标注"该板块数据暂缺"，继续组装。绝不让一个脆弱数据源拖垮整份攻略。

**为什么要子 Agent 而不是主 Agent 直接拉**：每个数据源返回的原始 JSON 很大（eBird 一个热点可能几百条观测）。子 Agent 在自己的上下文里消化，只把"高光鸟种 + 热点排名 + 关键提醒"这种攻略真正要用的结论带回来。

## Phase 2 · 组装输出（主 Agent）

1. **鸟种比对**：把 Phase 1 汇总的鸟种 vs **个人人生鸟单**比对，标记每个种是 `可加新`（没记录过，去了能加新种）还是 `已解锁`。这是攻略的"游戏化"亮点。
   - 人生鸟单优先读 `~/.birdwatch/lifelist.json`（来自中国观鸟记录中心，由 birdreport-logger 的 `lifelist.py` 生成/刷新），按鸟种**中文名**匹配。
   - 该文件不存在时，提示用户先刷新人生鸟单，或退回用户提供的 CSV；都没有就跳过标记。
2. **生成 HTML —— 优先用一键组装器**：

   ```
   python scripts/assemble_guide.py --name <点名> --lng <经度> --lat <纬度> --locId <eBird locId> \
       [--province 上海市 --city 上海市] [--out 观鸟攻略_<地点>.html]
   ```
   它内部编排 weather-forecast 的 `qweather_fetch.py`（跨 skill 子进程）+ `hotspot_detail`(含路网地图) + `birdreport_public`(点位级鸟种) + eBird 中文数据 + `target_select` 通勤，直接产出自包含离线 HTML，含以下板块（这是本 skill 的核心呈现规范）：

   - **🎯 高成功率·可加新（主板块，重点）**：用**点位级报告次数**(中国观鸟记录中心)排序=常见度，再 **× 拍摄难度因子**（杜鹃/小型莺/秧鸡/夜行鸮/雨燕等"闻声难见"种打折并标「难拍」），剔除偶现种。理念：**优先推成功率高的常见可加新种，而非容易空军的罕见种**。
   - **✨ 可遇不可求**：eBird 近14天罕见/高光**降级为彩蛋**，明确标"出现概率低、易空军、当惊喜别强求"。
   - **🗺️ 园内路线图**：`hotspot_detail` 生成的高德静态地图（🟠起=入口、🟢编号点位、**蓝线=沿真实道路的步行折线**），PNG 下载后 **base64 内嵌**——高德 key 留本地、**绝不写进 HTML**（可安全分享）。下方列编号点位+各段步行时长+沿途重点鸟种。
   - **⏰ 高频出鸟时段**：eBird checklist 提交时刻直方图 → 该点早/午高峰区间柱状图。
   - **☀️ 天气**、**🚇 通勤**(高德打车/公交，不自驾)、**📈 鸟况时间线**。
   - **🔴 鸟友情报（小红书）**：仅当 `xiaohongshu.enabled=true` 且本地有抓取结果时出现——把最近一次 `xhs_search.py` 抓的笔记（微点位/机位/季节提醒）按热度并入。组装时不联网，只读已抓 jsonl。`--xhs-location` 可指定过滤词（默认用 `--name`，建议传"滨江森林,滨森"这类避免同名干扰）。

   > 说明：`assemble_guide.py` 是把本会话沉淀的呈现逻辑固化的标准实现；个性化需求可在其输出基础上改，或参照 [assets/guide-template.html](assets/guide-template.html) 手工组装。**数据粒度诚实**：eBird/记录中心都没有"园内子点位级"鸟种，别把鸟种硬绑到具体子点位（那只能靠生境推断，除非用户要求否则不做）。

3. **保存 + 检查**：默认输出 `观鸟攻略_<地点>_<日期>.html`。`assemble_guide.py` 已自带自检（返回 `selfcheck_leak_or_placeholder` 应为 0）：① 文件独立可开（无外链）② 无残留 `{{...}}` ③ 无 amap key / eBird token 泄漏 ④ 缺失板块友好提示而非报错。

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
- **天气走兄弟 skill** `weather-forecast`（`scripts/qweather_fetch.py`）—— `assemble_guide.py` 已用绝对路径子进程调用并本地附加 `birdingHint`
- `scripts/birdreport_public.py` — 观鸟记录中心公开数据（区域鸟种名单 `--taxa --start --end`、报告/热点）。**limit≤50；505 不重试；月份用日期范围不用 taxon_month**
- `scripts/target_select.py` — **目标推荐**（Phase 0.5）：大本营→附近热点平衡打分（含高德打车/公交通勤）
- `scripts/species_hotspots.py` — **菜鸟聚集地**（Phase 0.5b）：可加新种→报告最集中点位，含月份对齐+周边多区+lift特异性+本地缓存。**重查询，严格低频**（见 Phase 0.5b 约束）
- `scripts/hotspot_detail.py` — **点内地图微攻略**：给定点位→几号门进/园内路线/步行时长/看什么鸟，并生成**真实道路折线的高德静态地图**（`--map-out`）+ **高频出鸟时段**(eBird checklist 时刻直方图)。Phase 2 路线图与时段板块都用它
- `scripts/xhs_search.py` — **小红书情报**（可选增强源，封装 MediaCrawler）：关键词搜公开笔记→按热度+地点过滤→返回摘要。`xiaohongshu.enabled` 默认关，遇验证码即放弃
- `scripts/assemble_guide.py` — **Phase 2 一键组装器**：编排上述脚本 + eBird 中文数据，直接产出带路网地图的自包含离线 HTML 攻略（稳拍降权榜/高光降级/时段柱图/通勤/🔴小红书情报[启用时]），自带泄漏与占位符自检

脚本都从 `~/.birdwatch/config.json`（env 回退）读 key，输出精简 JSON。

## 参考文档索引

- [references/ebird-api.md](references/ebird-api.md) — eBird key 申请 + 端点说明 + region code 查法
- 和风天气：见 [weather-forecast 的 references](../weather-forecast/references/qweather-api.md)（配置在 `~/.qweather/config.json`）
- [references/birdreport.md](references/birdreport.md) — 中国观鸟记录中心接入（社区工具，无官方 API）
- [references/xiaohongshu.md](references/xiaohongshu.md) — 小红书数据采集（MediaCrawler，注意合规风险）
- [references/sub-agent-prompts.md](references/sub-agent-prompts.md) — 4 个子 Agent 的任务 prompt 模板
