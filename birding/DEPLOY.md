# 观鸟工具套件 · 部署与使用（给新设备上的 Agent 读）

> 你（agent）读这份文档，就能在新设备上把这套"观鸟"能力装好并会用。
> 套件含 3 个 skill，统一配置在 `~/.birdwatch/config.json`。**仅供用户个人自用**；
> birdreport 相关功能涉及个人账号与逆向接口，请低频、善待平台。

## 1. 这是什么（3 个 skill 的分工）

| skill | 作用 | 触发 |
|-------|------|------|
| `birdwatching-guide` | 出**离线 HTML 观鸟攻略**：整合 eBird(观测/热点/罕见种) + 和风天气 + 观鸟记录中心公开数据 | "出个 XX 观鸟攻略" |
| `birdreport-logger` | **个人记录**：提交观鸟记录到 birdreport.cn + 维护人生鸟单 + 自动取 token | "记一笔观鸟记录" |
| `weekend-birding` | **编排**：把"行前出攻略 → 行后提交记录"串成一条龙，含可选 Obsidian/飞书 | "周末观鸟" |

数据源两条路（详见 birdwatching-guide/references/birdreport.md）：
- **公开数据**（区域鸟况/鸟种名单）走 `birdreport_public.py`（`/front/` 签名式，**无需登录 token**，只要 Node）
- **个人记录/可加新比对**走 `lifelist.py`/`submit.py`（`/member/` 需 `X-Auth-Token`）

## 2. 部署步骤（agent 按序执行）

### 2.1 放置 skill
把本目录下三个 skill 文件夹复制到该平台的 skills 目录（如 `~/.claude/skills/`），保持**各为顶层目录**：
`birdwatching-guide/`、`birdreport-logger/`、`weekend-birding/`

### 2.2 装依赖
- 必需：`pip install pycryptodome`（AES 解密）
- 公开鸟种/报告数据需 **Node.js + Google Chrome**，并在 `birdwatching-guide/scripts/birdreport/` 下：`npm install`（装 crypto-js、jsdom）
- 可选：`pip install playwright`（`grab_token.py` 自动抓 token 用系统 Chrome，无需 `playwright install`）

### 2.3 建配置 `~/.birdwatch/config.json`
复制模板 `birdwatching-guide/config.example.json` 到 `~/.birdwatch/config.json`，填：
- `ebird_api_key`：https://ebird.org/api/keygen （免费，2 分钟）
- `qweather.*`：和风天气 JWT。先生成 Ed25519 密钥对放 `~/.qweather/`（命令见 birdwatching-guide/references/qweather-api.md），公钥上传 https://dev.qweather.com 拿 `kid`/`sub`/`api_host`
- `birdreport.member_id`：用户的会员 id（个人记录用）
- `birdreport.token`：跑 `python birdreport-logger/scripts/grab_token.py` 自动获取并写入（首次在弹出 Chrome 登录一次，含验证码）

所有 key 优先读 config.json，env 作回退（`birdwatch_config.py` 负责）。

### 2.4 可选功能（config 开关，默认关）
- **Obsidian 双链图谱**：`obsidian.enabled=true` + `obsidian.vault_path`；跑 `lifelist.py` → `weekend-birding/scripts/obsidian_sync.py`（需 Dataview 插件）
- **飞书前端 cc-connect**：`ccconnect.enabled=true`；安装见 github.com/chenhg5/cc-connect。⚠️ 同一飞书 bot 不能两台机同时跑。

## 3. 怎么用

- **出攻略**：对用户的"周末去X出观鸟攻略"——按 birdwatching-guide/SKILL.md 的三阶段走（Phase1 并行采 eBird/天气/观鸟中心公开数据；Phase2 vs 人生鸟单标"可加新/已解锁"，填 HTML 模板）。
- **提交记录**：用户给"地点+日期+鸟种数量"——birdreport-logger 极简模板 → dry-run 预览 → `--submit`。**只提交用户真实观测**。
- **周末一条龙**：weekend-birding 编排行前/行后。

## 4. 关键坑（务必遵守）

1. **birdreport 公开接口 `limit` 必须 ≤50**（>50 必返 500/505）。
2. **不要对 birdreport 505 做 sleep 重试**——会阻塞会话（曾导致 cc-connect 卡死）；505 直接跳过/降级。
3. **公开鸟种名单按日期范围查**（`--taxa --start --end`），**不要用 `taxon_month`**（拿不到"今年某月"，返回 0）。
4. birdreport token 几天过期；过期重跑 `grab_token.py` 即可（写回 config.json，无需重启任何服务）。
5. 和风天气是 JWT 认证，每账号有专属 `api_host`，填错会 401/403。

## 5. 各 skill 细节
- `birdwatching-guide/DEPLOY.md`、`references/`（各数据源接入、API 申请步骤）
- `birdreport-logger/references/api.md`（birdreport 接口/字段/加密逆向记录）
- 三个 skill 各自的 `SKILL.md`（工作流）

## 6. birdwatching-guide 主要脚本（新设备直接可用）
- `assemble_guide.py` — **一键出攻略**：`--name --lng --lat --locId` → 带路网地图的离线 HTML（稳拍降权榜/高光降级/高频时段/通勤/可选小红书），自带泄漏自检
- `target_select.py` — 大本营→附近热点平衡推荐（可加新×丰富度×通勤）
- `species_hotspots.py` — **菜鸟聚集地**：可加新种→报告最集中点位，含月份对齐+周边多区+lift特异性+缓存。**重查询，严格低频**（结果缓存到 `~/.birdwatch/species_points_cache.json`，505 不重试）
- `hotspot_detail.py` — 点内路线：真实道路折线静态地图（`--map-out`）+ 高频出鸟时段
- `xhs_search.py` — **小红书情报（可选，默认关）**：封装 MediaCrawler。需另装 MediaCrawler（不在本仓），见 `birdwatching-guide/references/xiaohongshu.md`，**⚠️ xhshow 必须锁 0.1.9**，否则签名崩

## 7. 善待平台 / 合规红线
- birdreport：`limit≤50`、505 不重试、月份用日期范围；`species_hotspots` 小批+缓存，绝不一次猛扫
- 小红书：本人扫码登录、个人低频、遇验证码即放弃，不写绕过反爬代码；登录态(`browser_data/`)与 MediaCrawler 本体**不入仓**
- 所有真实 key/token/坐标只在 `~/.birdwatch/config.json`（gitignore），代码与仓库零硬编码
