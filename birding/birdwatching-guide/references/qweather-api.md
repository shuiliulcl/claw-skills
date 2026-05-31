# 和风天气（QWeather）API 接入（JWT 认证）

和风天气有官方免费 API，提供 3 天预报、降水、风向。本 skill 用 **JWT（EdDSA/Ed25519）** 认证——这是和风官方推荐的长期方式。API KEY 方式 2027-01-01 起会被限流、SDK5+ 不再支持，故不采用。

## 认证原理（理解后再操作）

JWT 不是一串固定 key，而是用**你本地的 Ed25519 私钥**现签的、最长 24h 过期的临时令牌。请求时放在头里 `Authorization: Bearer <token>`。脚本每次调用前自动签发，你不用手动管 token。

需要三样东西喂给脚本：
- **私钥**（本地保管，签名用）
- **kid**（凭证 ID，上传公钥后控制台给）
- **sub**（项目 ID）
- 外加你的专属 **API Host**

## 一次性设置步骤

### 1. 生成 Ed25519 密钥对
本 skill 已为本机生成，存放在 `C:/Users/<user>/.qweather/`：
- `ed25519-private.pem`（私钥，**勿外传、勿提交、勿放进 skill 目录**）
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
3. 在项目里「添加凭据」→ 选 **JWT/Ed25519**，把 `ed25519-public.pem` 的内容粘贴上传 → 拿到 **凭证 ID = kid**。
4. 在「设置 / API Host」找到你的专属 **API Host**（形如 `abcd1234.re.qweatherapi.com`）。v7 不用公共 host，填错会 401/403。

### 3. 设置环境变量
```powershell
[Environment]::SetEnvironmentVariable("QWEATHER_API_HOST","你的host","User")
[Environment]::SetEnvironmentVariable("QWEATHER_SUB","项目ID","User")
[Environment]::SetEnvironmentVariable("QWEATHER_KID","凭证ID","User")
# 私钥路径默认 C:/Users/<user>/.qweather/ed25519-private.pem，非默认路径才需设：
[Environment]::SetEnvironmentVariable("QWEATHER_PRIVATE_KEY","私钥路径","User")
```
重开终端生效。

## 端点与调用（已封装进 scripts/qweather_fetch.py）

3 天预报：`GET https://{host}/v7/weather/3d?location={经度,纬度}`，头带 `Authorization: Bearer <jwt>`。

**关键坑：`location` 是「经度,纬度」(lng,lat) 顺序，和 eBird 的 lat/lng 相反。** 脚本已处理，手动调用注意。

```bash
python scripts/qweather_fetch.py --lng 121.47 --lat 31.23
```

返回精简 JSON（3 天），每天含天气/气温/降水/风向/日出日落，外加脚本算的 `birdingHint` 观鸟建议。免费版约 1000 次/天，够用。

## 错误排查

- `401`/`403`：sub/kid 与私钥不匹配、公钥没上传成功、或没用专属 host。
- `404`：经纬度顺序填反或超范围。
- 缺 cryptography 库：`pip install cryptography`。
