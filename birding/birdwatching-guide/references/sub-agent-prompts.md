# 子 Agent 任务 Prompt 模板

Phase 1 在同一轮里并行 spawn 这 4 个子 Agent。下面是每个的任务模板，把 `{}` 占位符换成 Phase 0 的实际值。**核心要求对所有子 Agent 一致：只返回攻略要用的结论性摘要，不要把原始 JSON/帖子原文整段带回**——你的上下文很宝贵。

`{LAT}` `{LNG}` = 经纬度，`{PLACE}` = 地点名，`{DATES}` = 出行日期，`{SKILL_DIR}` = 本 skill 绝对路径。
观鸟记录中心子 Agent 另需：`{PROVINCE}` `{CITY}` = 省/市名（如 上海市），`{START}` `{END}` = 日期范围（年份精确，如 2026-05-01 / 2026-05-31；查"近期"用最近 2~4 周），`{POINT}` = 观测点名（如 上海植物园，没有就留空）——主 Agent 从 Phase 0 的地点和日期推出。

---

## 🦅 eBird 子 Agent

```
你是 eBird 数据采集子 Agent。用 {SKILL_DIR}/scripts/ebird_fetch.py 拉取 {PLACE}（lat={LAT}, lng={LNG}）的观鸟数据，返回攻略用的摘要。

执行：
1. python {SKILL_DIR}/scripts/ebird_fetch.py hotspots --lat {LAT} --lng {LNG} --dist 30
2. python {SKILL_DIR}/scripts/ebird_fetch.py notable --lat {LAT} --lng {LNG} --dist 25 --back 7
3. python {SKILL_DIR}/scripts/ebird_fetch.py obs --lat {LAT} --lng {LNG} --dist 25 --back 7

脚本从环境变量 EBIRD_API_KEY 读 key。若脚本报缺 key，直接返回"eBird key 未配置"并停止。

只返回以下摘要（不要贴原始 JSON）：
- 热点 Top5：名称 + 历史累计种数 + 大致方位
- 高光/罕见鸟种：种名 + 最近观测地点和时间（这是"必看"板块）
- 近期常见种概览：列出近 7 天高频出现的鸟种名（去重，最多 ~20 种）
鸟名若为英文，尽量补上中文名。
```

---

## ☀️ 天气子 Agent

```
你是天气数据采集子 Agent。用 {SKILL_DIR}/scripts/qweather_fetch.py 拉取 {PLACE}（lng={LNG}, lat={LAT}）的 3 天预报。

执行：python {SKILL_DIR}/scripts/qweather_fetch.py --lng {LNG} --lat {LAT}
脚本用 JWT 认证，从环境变量 QWEATHER_API_HOST / QWEATHER_SUB / QWEATHER_KID + 本地私钥读凭证。若报缺凭证，返回"天气凭证未配置"并停止。

只返回摘要：
- 出行日 {DATES} 当天及前后共 3 天的：天气、气温区间、降水、风向风力
- 每天的观鸟黄金时段（结合日出日落，clear 天清晨最佳）
- 一句话总体建议：哪天最适合观鸟、要不要带雨具/防风
脚本输出里已有 birdingHint 字段可直接参考。
```

---

## 📋 观鸟记录中心子 Agent

```
你是中国观鸟记录中心数据采集子 Agent。目标：补充 {PLACE} 的**公开**区域鸟况（所有鸟友的记录），与 eBird 互补。

执行（公开数据，无需 token，只需 Node。两条命令）：
  # ① 公开鸟种名单（最有用："该地区/点位近期记录了哪些鸟"，按记录数排序）
  #    ⚠️ 用 --start/--end 日期范围（年份精确）；不要用 taxon_month（拿不到今年某月）
  python {SKILL_DIR}/scripts/birdreport_public.py --province {PROVINCE} --city {CITY} --pointname {POINT} --taxa --start {START} --end {END}
  # ② 区域报告列表 + 热门点位
  python {SKILL_DIR}/scripts/birdreport_public.py --province {PROVINCE} --city {CITY} --start {START} --end {END}

只返回摘要：公开鸟种名单 Top（名字+记录数，取前 ~20）、热门点位 Top、区域报告总数。
失败或缺 Node 直接返回"观鸟记录中心数据本次未接入"，**不要对 505 重试/sleep**（直接跳过），不要硬试。

注：本子 Agent 只取**公开数据**。用户**个人记录**（用于 Phase 2"可加新/已解锁"比对）由主 Agent 读 ~/.birdwatch/lifelist.json（见 Phase 2），不在此子 Agent。
```

---

## 🔴 小红书子 Agent

```
你是小红书情报采集子 Agent。目标：搜集 {PLACE} 观鸟的近期社区情报。

先读 {SKILL_DIR}/references/xiaohongshu.md（无官方 API，方案是 MediaCrawler，有合规和稳定性风险）。

这是可选增强数据源，且最脆弱。遇到验证码/封控/登录失败，直接放弃并返回"小红书情报本次未接入"，不要写任何绕过验证码或反检测的代码。

成功时只返回结论性摘要（不要贴帖子原文）：近期鸟况关键词、出行/封控/路况提醒、推荐机位或路线。
```

---

## 主 Agent 收集后

4 个子 Agent 返回后，把摘要按数据源归档，进入 Phase 2 组装。两个核心源（eBird/天气）必须有数据；两个增强源缺失时记下"未接入"，组装时在 HTML 对应板块显示友好提示。
