---
name: weather-forecast
description: 查询未来 3 天天气预报（基于和风天气 JWT API）。当用户问"明天天气怎么样"、"未来三天天气"、"会下雨吗"、"查一下 XX 的天气"、"weather"、"forecast"、"3-day forecast"、"will it rain"，或在出行规划中需要天气数据时使用。支持城市名（中文/英文）和经纬度两种输入。**不要在 birdwatching-guide 内部主动触发本 skill**——观鸟攻略已直接调用同一脚本。
---

# weather-forecast

和风天气 v7 的 3 天预报封装，JWT (EdDSA/Ed25519) 鉴权。城市名解析走高德地理编码（和风 GeoAPI 默认项目安全策略会 403，且高德对中文行政区名更稳）。

## 用法

```bash
# 城市名（中文 / 英文都行；带省市前缀更准）
python scripts/qweather_fetch.py --city 上海
python scripts/qweather_fetch.py --city "上海市中山公园"

# 经纬度（lng 在前、lat 在后，别填反）
python scripts/qweather_fetch.py --lng 121.47 --lat 31.23
```

输出 JSON：
```json
{
  "daily": [
    {"date":"2026-06-26","textDay":"多云","textNight":"阴",
     "tempMax":"29","tempMin":"22","precip":"0.5",
     "windDirDay":"东风","windScaleDay":"1-3","humidity":"76",
     "sunrise":"04:52","sunset":"19:03"}
  ],
  "resolved": {  // 仅 --city 时出现
    "name":"上海市","province":"上海市","city":"上海市",
    "adcode":"310000","lng":"121.473667","lat":"31.230525"
  }
}
```

回复用户时**给摘要而非粘 JSON**：天气状况、温度、降水、风力，一两句话即可。

## 配置

集中在 `~/.qweather/config.json`（flat schema）：

```json
{
  "api_host": "abcd1234.re.qweatherapi.com",
  "sub": "项目ID",
  "kid": "凭证ID",
  "private_key_path": "C:/Users/banqiang/.qweather/ed25519-private.pem"
}
```

私钥 PEM 本地保管。高德 key 用于城市名解析，按以下顺序自动找：
1. `~/.qweather/config.json` 的 `amap_key` 字段
2. `~/.amap/config.json` 的 `amap.key` 或 `key`
3. `~/.birdwatch/config.json` 的 `amap.key`
4. 环境变量 `AMAP_KEY`

只用经纬度模式不需要高德 key。

配置申请与坑详见 [references/qweather-api.md](references/qweather-api.md)。

## 依赖

- Python `cryptography` 库（`pip install cryptography`），用于签 JWT
- 城市名模式：高德 key（参见 [map-tools](../map-tools/SKILL.md) 同一份 key）

## 限额

和风免费版 1000 次/天，预报数据。

## 不做的事

- 实时天气 / 逐小时 / 7 天 / 灾害预警 / 生活指数（按需扩 endpoint）
- 反向解析（坐标→城市）
- 城市歧义消解 UI（高德默认返回首个匹配，必要时用户加省市前缀）
