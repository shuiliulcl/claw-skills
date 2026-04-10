---
name: game-watch
description: 新游动态监控 Skill。抓取 iOS 畅销/免费榜（七麦数据）、TapTap 评分/关注，输出结构化 JSON 供 cron agent 分析并推送飞书。
read_when:
  - 监控新游上线后的市场表现
  - 获取 iOS App Store 畅销/免费榜单数据
  - 获取 TapTap 评分、关注人数、评论数
  - 生成新游动态日报
metadata:
  requires:
    bins: ["node"]
    files:
      - "game-watch-config.json"   # 主配置（cookie路径、榜单、追踪游戏）
      - "scripts/cookies.txt"       # 七麦/TapTap cookie（Netscape格式，由用户提供）
---

# Game Watch Skill

## 架构

```
game-watch-config.json   ← 配置：cookie路径、榜单设置、追踪游戏列表
scripts/
  fetch-ios-charts.js    ← 抓取七麦 iOS 榜单（畅销总榜/畅销游戏榜/免费总榜）
  fetch-taptap.js        ← 抓取 TapTap 评分/关注数据
```

## 数据来源

| 数据 | 来源 | 获取方式 |
|------|------|----------|
| iOS 畅销总榜 | 七麦数据 `api.qimai.cn` | Node.js HTTP + cookie |
| iOS 畅销游戏榜 | 七麦数据 | 同上，brand=game_paid |
| iOS 免费总榜 | 七麦数据 | 同上，brand=free |
| TapTap 评分/关注 | `www.taptap.cn/webapiv2` | Node.js HTTP + X-UA header + cookie |

## 运行方式

```bash
# 获取今日 iOS 榜单
node scripts/fetch-ios-charts.js

# 获取指定日期
node scripts/fetch-ios-charts.js 2026-04-10

# 指定配置文件
node scripts/fetch-ios-charts.js -config /path/to/game-watch-config.json

# 获取 TapTap 数据（追踪配置中的游戏）
node scripts/fetch-taptap.js
```

## 配置文件说明

```json
{
  "cookie_file": "绝对路径/cookies.txt",   // Netscape格式，需包含七麦和TapTap的登录cookie

  "ios_charts": {
    "enabled": true,
    "country": "cn",           // 国家：cn/us/jp
    "device": "iphone",        // 设备：iphone/ipad
    "top_n": 30,               // 每个榜单取前N名
    "brands": [
      { "id": "paid",      "label": "畅销总榜" },
      { "id": "game_paid", "label": "畅销游戏榜" },
      { "id": "free",      "label": "免费总榜" }
    ]
  },

  "tracked_games": [
    {
      "name": "游戏名称",
      "taptap_id": 744415,       // TapTap app id（从URL获取）
      "ios_app_id": "",          // iOS App Store id（可选）
      "note": "备注"
    }
  ]
}
```

## Cookie 更新

Cookie 有效期约 30 天。过期后：
1. 用浏览器登录七麦（qimai.cn）和 TapTap（taptap.cn）
2. 用 EditThisCookie 等插件导出 Netscape 格式
3. 替换 `cookies.txt` 文件

## 输出格式

### iOS 榜单（fetch-ios-charts.js）

```json
{
  "date": "2026-04-10",
  "charts": {
    "paid": {
      "label": "畅销总榜",
      "list": [
        { "rank": 1, "appId": "xxx", "name": "拣爱", "publisher": "...", "price": "18.00" }
      ]
    }
  }
}
```

### TapTap（fetch-taptap.js）

```json
{
  "fetched_at": "2026-04-10T06:00:00.000Z",
  "games": [
    {
      "appId": 744415,
      "title": "王者荣耀世界",
      "rating": 7.2,
      "fans": 2602465,
      "reviews": 1234,
      "reserves": 567890,
      "url": "https://www.taptap.cn/app/744415"
    }
  ]
}
```

## 典型 Cron 用法

cron agent 调用示例（每日09:30）：

```
1. node scripts/fetch-ios-charts.js → 得到榜单JSON
2. node scripts/fetch-taptap.js → 得到评分JSON
3. 分析数据：追踪游戏是否进入榜单、评分变化、关注涨幅
4. 推送飞书：格式化日报消息
```
