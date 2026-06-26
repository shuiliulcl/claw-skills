# 和风天气（QWeather）API 接入（JWT 认证）

和风天气有官方免费 API，提供 3 天预报、降水、风向。本 skill 用 **JWT（EdDSA/Ed25519）** 认证——和风官方推荐的长期方式。API KEY 方式 2027-01-01 起会被限流、SDK5+ 不再支持，故不采用。

## 认证原理

JWT 不是固定 key，而是用**你本地的 Ed25519 私钥**现签的、最长 24h 过期的临时令牌。请求时放头里 `Authorization: Bearer <token>`。脚本每次调用前自动签发，你不用手动管 token。

需要四样东西：
- **私钥**（本地保管，签名用）
- **kid**（凭证 ID，上传公钥后控制台给）
- **sub**（项目 ID）
- 专属 **API Host**

## 一次性设置

### 1. 生成 Ed25519 密钥对

本机已生成在 `C:/Users/banqiang/.qweather/`：
- `ed25519-private.pem`（私钥，**勿外传、勿提交**）
- `ed25519-public.pem`（公钥，用于上传控制台）

若要重新生成：
```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
k = Ed25519PrivateKey.generate()
open("ed25519-private.pem","wb").write(k.private_bytes(s.Encoding.PEM,s.PrivateFormat.PKCS8,s.NoEncryption()))
open("ed25519-public.pem","wb").write(k.public_key().public_bytes(s.Encoding.PEM,s.PublicFormat.SubjectPublicKeyInfo))
```
（依赖 `pip install cryptography`）

### 2. 控制台配置

1. 登录 https://dev.qweather.com/ ，实名为个人开发者（免费）。
2. 新建项目（Web API），记下 **项目 ID = sub**。
3. 在项目里「添加凭据」→ 选 **JWT/Ed25519**，把 `ed25519-public.pem` 内容粘贴上传 → 拿到 **凭证 ID = kid**。
4. 在「设置 / API Host」找到你的专属 **API Host**（形如 `abcd1234.re.qweatherapi.com`）。v7 不用公共 host，填错会 401/403。

### 3. 写配置文件

`~/.qweather/config.json`（flat schema）：
```json
{
  "api_host": "abcd1234.re.qweatherapi.com",
  "sub": "...",
  "kid": "...",
  "private_key_path": "C:/Users/banqiang/.qweather/ed25519-private.pem"
}
```

环境变量也支持（`QWEATHER_API_HOST` / `QWEATHER_SUB` / `QWEATHER_KID` / `QWEATHER_PRIVATE_KEY`），优先级低于 config.json。

## 端点说明

### 天气 3 天预报（已封装）

```
GET https://{api_host}/v7/weather/3d?location={lng,lat}
Authorization: Bearer <jwt>
```

**关键坑**：`location` 是「**经度,纬度**」(lng,lat) 顺序，和 eBird 等 lat/lng 反着来。脚本已处理。

### 城市名 → 坐标（用高德，而非和风 GeoAPI）

和风 GeoAPI 端点是 `https://{api_host}/geo/v2/city/lookup?location={name}`，**但默认项目安全策略下会返回 `403 Security Restriction`**——除非你去控制台关掉 IP/Referer 限制或显式给 GeoAPI 加权限。

本 skill 直接用高德地理编码 `https://restapi.amap.com/v3/geocode/geo?address={name}&key={amap_key}` 替代：
- 不需要 JWT，简单
- 对中文行政区名解析更稳
- 用户多半已为别的 skill（map-tools / birdwatching-guide）配过高德 key

amap_key 查找顺序见 [SKILL.md](../SKILL.md#配置)。

## 错误排查

- `401`/`403`：sub/kid 与私钥不匹配、公钥没上传成功、或没用专属 host
- 调用 GeoAPI 拿到 `403 Security Restriction`：项目安全策略限制——本 skill 已绕开，改用高德
- `404`：经纬度顺序填反或超范围
- 缺 cryptography：`pip install cryptography`

## 限额

和风免费版 1000 次/天，足够个人/小工作流使用。
