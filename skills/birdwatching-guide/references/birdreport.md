# 中国观鸟记录中心（birdreport.cn）接入

**没有公开官方 API**，本 skill 通过逆向客户端加密接入（增强数据源）。拿到锦上添花，拿不到就跳过，**绝不因它失败而中断整份攻略**。

## 接入机制（已实现）

脚本 `scripts/birdreport_fetch.py` 跑站点原版加密 JS（execjs + Node），流程：
- 请求参数 RSA 加密、响应体 AES-256-CBC 解密、`sign = md5(format_data + requestId + timestamp)`
- 端点：`/front/record/activity/search`（按地区+日期搜报告）、`/front/activity/taxon`（取某报告鸟种）
- **当前接口需登录鉴权头 `X-Auth-Token`**（2023 旧版无需，现已加上）。缺 token 会返回 `code 500 系统出错`。

依赖（已随 skill 装好）：
- `pip install PyExecJS` + 本机 Node.js
- `scripts/birdreport/jQuertAjax.js`（站点加密逻辑）
- `scripts/birdreport/node_modules/`（`crypto-js`、`jsdom`）

## 怎么拿 X-Auth-Token

1. 浏览器登录 http://www.birdreport.cn/ （需有观鸟记录中心账号）。
2. F12 打开开发者工具 → Network（网络）面板。
3. 在站内点开「记录查询」或个人中心，触发任意接口请求。
4. 在请求列表里点一条 `api.birdreport.cn` 的请求 → Headers → 找到请求头 **`X-Auth-Token`**，复制它的值。
5. 设环境变量：
   ```powershell
   [Environment]::SetEnvironmentVariable("BIRDREPORT_TOKEN","你的token","User")
   ```
   ⚠️ 网页重新登录会导致 token 变化，失效后需重新复制。

## 调用示例

```bash
python scripts/birdreport_fetch.py --province 上海市 --city 上海市 --start 2026-05-22 --end 2026-05-29 --max-checklists 12 --delay 0.6
```
输出：报告份数 + 鸟种汇总（去重含出现次数）+ 报告点位。

## 合规与礼貌（务必遵守）

- 仅用于**个人、低频**观鸟规划，脚本内置 `--delay` 限速，别调太小、别翻太多页。
- 数据版权属记录中心及记录者，攻略引用应注明来源「中国观鸟记录中心」。
- 这是公益平台，善待它。遇到失败不要硬刷、不要绕过任何校验。

## 两条路：公开数据 vs 个人记录（重要）

birdreport 有两套并存的 API，用途不同：

| | 脚本 | 端点 | 鉴权 | 数据 |
|--|------|------|------|------|
| **公开数据** | `birdreport_public.py` | `/front/record/...` | **签名式**（requestId/sign/timestamp + RSA body），**无需登录 token** | **所有鸟友**在某地区的公开报告（如上海某周 829 份）|
| **个人记录** | `birdreport_fetch.py` / `lifelist.py` | `/member/system/...` | `X-Auth-Token`（需登录，会过期）| 本账号自己的记录 / 人生鸟单 |

- 攻略的"区域鸟况/热门点位"应走 **公开数据**（`birdreport_public.py`，无 token，最省心）。
- "可加新/已解锁"比对走 **个人记录**（`lifelist.py`）。

**公开数据机制**（qBird 老方案，仍有效）：format(排序JSON) → RSA 加密 body → `sign=md5(明文+requestId+timestamp)` → 响应 AES 解密（不同端点 key 不同，两 key 都试）。加解密在 Node 助手 `scripts/birdreport/front_helper.js`（用站点原版 jQuertAjax）。

**已知端点（均 POST 签名式，无需 token）：**
- `/front/record/chart/summary` — 区域汇总：报告数/记录数/鸟种数（稳定）
- `/front/record/activity/taxon` — **公开鸟种名单**（用 `startTime`/`endTime` 日期范围 + `version=CH4` + 地区/点位）；字段 `taxonname`(中文)/`recordcount`/`latinname`/`taxon_id`。**这是"区域有哪些鸟"的来源**。⚠️ 用日期范围（年份精确）；`taxon_month`（仅月份）拿不到"今年某月"，会返回 0
- `/front/record/activity/search` — 公开报告列表+点位
- `/front/record/search/TaxonCountBar`、`ReportCountBar` — 月度统计

**⚠️ 两个铁律**：① `limit` 必须 **≤50**（>50 必 500/505）② **不要对 505 做 sleep 重试**（曾导致会话卡死）。

```bash
# 区域公开鸟种名单（按日期范围，年份精确；上海植物园）
python scripts/birdreport_public.py --province 上海市 --city 上海市 --pointname 上海植物园 --taxa --start 2026-05-01 --end 2026-05-31
# 区域报告列表+热门点位
python scripts/birdreport_public.py --province 上海市 --city 上海市 --start 2026-05-20 --end 2026-05-29
```

## ⚠️ 服务端限制与踩坑记录（2026-05 实测）

`/front/record/activity/search` 这个端点对客户端有两道现实约束，文档里没写，调用前必须知道：

### 1. `limit` 上限是 50

服务端对单页大小做了硬限制，超过就返 `code=500 系统出错！`，且**没有任何提示**说原因是 limit。本机实测：

| limit | 6 次成功率 |
|-------|--------|
| 10 | 6/6 ✅ |
| 50 | 6/6 ✅ |
| 100 | 0/6 ❌ 必 500 |

脚本默认值已改为 `--limit 50`，并提供 `--pages N` 分页聚合（默认 3 页 = 150 份）。**绝不要再调到 100**——之前曾因此误判成"端点失效"绕了一大圈。

### 2. 高频请求触发限流（`code=505`）

短时间内（几秒内）多次调用 `/front/record/activity/search` 会返 `code=505`，且**持续数分钟**才恢复。这是平台反爬，不是你的请求错了。

应对：
- 脚本里 `time.sleep(0.6)` 限速分页（已实现）
- 调试时**不要循环刷新**——一旦 505，停手等 5-10 分钟，否则窗口会被拉得更长
- 同 host 下 `/front/record/search/{TaxonCountBar,ReportCountBar}` 不受这道限流影响，可以作为"探活"端点

### 3. 想查某个点位的近期记录

接口 body 有 `pointname` 字段，但服务端对它的过滤行为没验证清楚（疑似精确匹配 + 触发 505 风险）。**推荐走客户端过滤**：

```python
# 1. 拉区域多页（已实现）
all_rows = fetch_pages(province='上海市', city='上海市',
                       start='2026-05-21', end='2026-05-30', pages=3)
# 2. 本地按 point_name 子串匹配（稳定，不刺激服务端）
century = [r for r in all_rows if '世纪公园' in r['point_name']]
# 3. 用 serial_id 下钻到具体鸟种
for r in century:
    taxa = front_call('/front/activity/taxon', {'serial_id': r['serial_id']})
```

`/front/activity/taxon` 端点是已知的"取某份报告里的鸟种列表"接口（references 顶部"接入机制"段已提）。

## 子 Agent 拿不到数据时

直接返回"观鸟记录中心数据本次未接入/获取失败"，主 Agent 在 HTML 对应板块显示友好提示，攻略其余部分照常生成。
