# eBird API 2.0 接入

eBird 是康奈尔鸟类学实验室的全球观测数据库，**有官方免费 API**，是本 skill 最可靠的数据源。

## 申请 API Key（约 2 分钟，免费）

1. 注册/登录 eBird 账号：https://secure.birds.cornell.edu/cassso/login
2. 打开 key 申请页：https://ebird.org/api/keygen
3. 页面会直接显示一串 token（你的 API key），复制它。
4. 设置环境变量（脚本从这里读）：
   - Windows PowerShell（永久）：`[Environment]::SetEnvironmentVariable("EBIRD_API_KEY","你的key","User")`，重开终端生效。
   - 临时（当前会话）：`$env:EBIRD_API_KEY = "你的key"`

> key 不绑定额度上限，但请合理调用（eBird 要求轻量使用）。

## region code（地区代码）怎么查

eBird 用层级代码标识地区：国家 `CN` → 省 `CN-11`(北京) → 区县。攻略里用经纬度端点通常就够了，不一定需要 region code。如确需：

- 列出中国所有省级代码：`GET /v2/ref/region/list/subnational1/CN`（带 `x-ebirdapitoken` 头）
- 常见：北京 `CN-11`、上海 `CN-31`、广东 `CN-44`、云南 `CN-53`、四川 `CN-51`。

## 本 skill 用到的端点（已封装进 scripts/ebird_fetch.py）

所有请求都要带请求头 `x-ebirdapitoken: <key>`。base URL：`https://api.ebird.org/v2`

| 用途 | 端点 | 脚本子命令 |
|------|------|-----------|
| 附近近期观测 | `/data/obs/geo/recent?lat=&lng=&dist=&back=` | `obs` |
| 附近罕见/高光鸟种 | `/data/obs/geo/recent/notable?lat=&lng=&dist=&back=` | `notable` |
| 附近热点 | `/ref/hotspot/geo?lat=&lng=&dist=&fmt=json` | `hotspots` |

- `dist`：半径公里，最大 50。
- `back`：回溯天数，最大 30，攻略一般用 7。
- 热点脚本会按 `numSpeciesAllTime`（历史累计种数）降序，方便取 Top5。

## 调用示例

```bash
# 北京附近 25km、近 7 天的观测
python scripts/ebird_fetch.py obs --lat 39.90 --lng 116.40 --dist 25 --back 7

# 附近高光/罕见鸟种（攻略的"必看"板块）
python scripts/ebird_fetch.py notable --lat 39.90 --lng 116.40 --dist 25 --back 7

# 附近热点 Top（输出已按累计种数排序，取前 5）
python scripts/ebird_fetch.py hotspots --lat 39.90 --lng 116.40 --dist 30
```

## 鸟名本地化提示

eBird 默认返回英文俗名（`comName`）。如需中文鸟名，可在请求加 `&sppLocale=zh_SIM`（简体中文），或在组装 HTML 时由子 Agent 补译。脚本目前透传 eBird 返回的 `comName`，需要中文时让子 Agent 翻译或调整脚本加 locale 参数。
