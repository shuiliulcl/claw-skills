# 观鸟工具部署指南（多机自用）

三个 skill 组成：`birdwatching-guide`（出攻略）、`birdreport-logger`（个人记录/鸟单）、
`weekend-birding`（编排 + 可选 Obsidian/飞书）。所有机器相关项集中在**一份** `~/.birdwatch/config.json`。

> 仅供个人自用。birdreport 相关功能涉及个人账号，请低频、善待平台。

## 1. 前置依赖

- **Python 3.10+**：`pip install pycryptodome`（必需，AES 解密）
- 可选 `pip install playwright`（仅 `grab_token.py` 自动抓 token 用；用系统 Chrome，无需 `playwright install`）
- 可选 Node.js + Google Chrome（grab_token 用系统 Chrome）
- 可选 cc-connect + pm2（仅飞书前端用）

## 2. 放置 skill

把这三个目录拷到新机的 skills 目录（如 `~/.claude/skills/`）：
`birdwatching-guide/`、`birdreport-logger/`、`weekend-birding/`
（每个 skill 的 `scripts/` 里都自带一份 `birdwatch_config.py`，无需额外操作。）

## 3. 建配置 `~/.birdwatch/config.json`

复制 `birdwatching-guide/config.example.json` 到 `~/.birdwatch/config.json`，按下面填：

### eBird（必填，免费）
`ebird_api_key`：https://ebird.org/api/keygen 申请，详见 `birdwatching-guide/references/ebird-api.md`

### 和风天气（必填，免费，JWT）
1. 生成 Ed25519 密钥对（放 `~/.qweather/`）：
   ```python
   from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
   from cryptography.hazmat.primitives import serialization as s
   import os; os.makedirs(os.path.expanduser("~/.qweather"), exist_ok=True)
   k=Ed25519PrivateKey.generate()
   open(os.path.expanduser("~/.qweather/ed25519-private.pem"),"wb").write(k.private_bytes(s.Encoding.PEM,s.PrivateFormat.PKCS8,s.NoEncryption()))
   open(os.path.expanduser("~/.qweather/ed25519-public.pem"),"wb").write(k.public_key().public_bytes(s.Encoding.PEM,s.PublicFormat.SubjectPublicKeyInfo))
   ```
   （需 `pip install cryptography`）
2. 把 `ed25519-public.pem` 上传到 https://dev.qweather.com 控制台 → 拿 `kid`/`sub`/`api_host`，填进 config。详见 `references/qweather-api.md`。

### 中国观鸟记录中心（可选，个人记录/可加新比对）
- `birdreport.member_id`：你的会员 id。
- `birdreport.token`：跑 `python birdreport-logger/scripts/grab_token.py` 自动获取并写入（首次在弹出的 Chrome 里登录一次）。token 几天过期，过期再跑一次即可。

## 4. 可选功能（默认关闭）

### Obsidian 双链图谱
config 设 `obsidian.enabled=true` + `obsidian.vault_path`，然后：
```
python birdreport-logger/scripts/lifelist.py           # 先拉人生鸟单
python weekend-birding/scripts/obsidian_sync.py        # 生成物种笔记+仪表盘
python weekend-birding/scripts/import_history.py       # 导入历史出行(可选)
```
需 Obsidian 装 Dataview 插件。

### 飞书前端（cc-connect）
config 设 `ccconnect.enabled=true` + `run_js`/`cwd`。安装见 https://github.com/chenhg5/cc-connect ，用 pm2 托管。
> ⚠️ **同一个飞书 bot 不能在两台 PC 同时跑**（会抢着回复）。多机要么同时只开一台，要么第二台用另一个 bot。
> cc-connect 用的 ANTHROPIC 等模型凭证走它自己的环境/claude 设置，与本配置无关。

## 5. 用法速查

```
# 出攻略数据源（主 Agent 会编排，也可单独调）
python birdwatching-guide/scripts/ebird_fetch.py hotspots --lat 31.23 --lng 121.47 --dist 30
python birdwatching-guide/scripts/qweather_fetch.py --lng 121.47 --lat 31.23
# 个人记录
python birdreport-logger/scripts/lifelist.py
python birdreport-logger/scripts/submit.py 记录.txt            # dry-run
python birdreport-logger/scripts/submit.py 记录.txt --submit   # 提交
# token 过期了
python birdreport-logger/scripts/grab_token.py                 # 自动抓并写入 config
```

## 配置优先级
所有 key：`config.json` 优先 → 环境变量回退。所以旧的"环境变量"方式仍可用，但推荐统一用 config.json。
