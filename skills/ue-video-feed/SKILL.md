---
name: ue-video-feed
description: 拉取 Unreal Engine 官方 YouTube 频道最新视频,与飞书 Base 待看列表去重后写入新增,并通过飞书私聊推送清单。当用户说"刷一下 UE 视频""检查虚幻官方频道""更新 UE 视频列表""UE 频道新视频""看看虚幻最近发了啥""有没有虚幻新视频"时使用。也可挂定时任务自动调用,无参数即可执行。
metadata:
  requires:
    bins: ["lark-cli", "python"]
---

# UE 视频订阅

定期同步 Unreal Engine 官方 YouTube 频道(`UCBobmJyzsJ6Ll7UbfhI4iwQ`)最新上传到飞书多维表格「UE 视频待看列表」,新增视频自动推送私聊。

## 调用方式

直接跑脚本,无参数:

```powershell
python "C:\Users\banqiang\.claude\skills\ue-video-feed\scripts\fetch.py"
```

也可以挂定时任务(/loop 或系统任务计划)。

## 前置条件

1. **本地配置文件** `%USERPROFILE%\.config\ue-video-feed\config.json` 存在,必填字段:
   ```json
   {
     "youtube_api_key": "你的_YOUTUBE_DATA_API_V3_KEY",
     "base_token": "你的飞书 Base token",
     "table_id": "你的目标 table_id",
     "user_open_id": "DM 推送目标的飞书 open_id"
   }
   ```
   可选字段:`channel_id`(默认 UE 官方频道)、`anthropic_api_key` / `anthropic_base_url` / `anthropic_model`(用于自动翻译中文标题,缺失时回退到环境变量)。完整模板见 skill 目录下 `config.template.json`。
2. **lark-cli 已用 user 身份登录**(`lark-cli auth status` 显示 user identity ready),user scope 必须包含 `base:record:read`、`base:record:create`。
3. **lark-cli bot 身份 ready**,bot 用于 DM 推送(papergames 组织限制了 user 的 `im:message.send_as_user` scope,所以 IM 推送走 bot,不要试图加这个 user scope)。
4. Python 3.7+ 在 PATH 中。

## 关键资源

所有这些都从 config.json 读取,以下值是当前 papergames 实例配置(其他设备 / 其他人 fork 时改 config 即可):

- **频道**: Unreal Engine 官方 - `UCBobmJyzsJ6Ll7UbfhI4iwQ`(`channel_id` 默认值)
- **Base**: `SpvXbLleeaQQMusl2bQcd04pncc` / 表 `tblhyTM6a1bDlybm`(URL: https://papergames.feishu.cn/base/SpvXbLleeaQQMusl2bQcd04pncc)
- **私聊接收人**: 半墙 - `ou_2b6334604d63123d4dc232d596e9d46d`

## Base 字段

| 字段 | 类型 | 用途 |
|---|---|---|
| 中文标题 | text(primary) | 用户填写的中文翻译/概括,第一列 |
| 英文标题 | text | 来自 YouTube 的原标题 |
| 链接 | text(url) | YouTube 视频链接 |
| 时长 | text | 形如 12:34 或 1:23:45 |
| 发布时间 | datetime | yyyy-MM-dd HH:mm |
| 状态 | select | 新发现 → 想看 → 已存档 / 已忽略 |
| 备注 | text | 用户筛选时手填,做完笔记后可贴 wiki 链接 |
| 视频ID | text | YouTube videoId,作为去重主键(脚本读这个) |

新写入记录默认状态=「新发现」,中文标题留空。

## 行为

1. 调 YouTube API 拉频道最新 50 条上传 + 时长
2. **过滤**: 时长 < 10 分钟,或标题命中"非开发"模式(预告/直播预告/活动通知等),直接跳过
3. 拉 Base 现有 视频ID 集合
4. 按 videoId 筛新增
5. 新增写入 Base(状态=新发现),并发飞书私聊一条 markdown 清单
6. 0 新增静默退出,不推送

YouTube 配额成本约每次 3 units(channels.list 1 + playlistItems.list 1 + videos.list 1),uploads playlist 缓存到 config 目录后只剩 2 units。

## 视图

Base 共 4 个视图,**新发现 是默认视图**(view 列表里排第一,Base 打开默认进它):

| 视图 | view_id | 筛选 | 用途 |
|---|---|---|---|
| 新发现 | vew1jsRuRB | 状态=新发现 | 默认入口,挑想看的 |
| 想看 | vewiR9Dim5 | 状态=想看 | 待看片单 |
| 已存档 | vewDJoLKHE | 状态=已存档 | 已看 + 已写笔记 |
| 全部 | vewIKFmcN2 | 无 | 包含已忽略,看全集时用 |

四个视图都按 发布时间 倒序,列序 中文标题 → 英文标题 → 链接 → 时长 → 发布时间 → 状态 → 备注 → 视频ID。

## 过滤规则

代码里两个常量,改它们就改过滤行为:

- `MIN_DURATION_SEC` (当前 600 = 10 min): 时长不足直接跳过
- `NON_DEV_TITLE_PATTERNS`: 正则列表,标题命中任一即视为非开发主题

当前活跃模式族(详见 fetch.py):

- 营销/活动: `trailer` / `out now` / `available now` / `tune in` / `join us live` / `this just in` / `this time next week` / `live next week|tomorrow|today` / `coming|launching next|in`
- 非主线产品: `UEFN` / `Creating in Fortnite` / `MetaHuman`(数字人/角色资产工具链)

调整规则后,运行 `python scripts/cleanup.py` 可以把 Base 里已存在但按新规则该刷掉的记录批量标记为「已忽略」(不删除,保留追溯)。

## 中文标题

新视频写入时若有可用的 Anthropic API,会调 Claude Haiku 4.5 批量翻译当次新增标题(单次 API 调用处理所有新增,带 prompt caching),写入 `中文标题` 字段并在私聊推送时优先展示中文。

**鉴权与中转**:fetch.py 优先读 config.json 里的 `anthropic_api_key` / `anthropic_base_url` / `anthropic_model`,缺失时回退到 `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` 环境变量。

- 走官方 Anthropic: base_url 默认 `https://api.anthropic.com`,鉴权头用 `x-api-key`
- 走 PaperHub 等中转: base_url 设为 `https://tc-paperhub.diezhi.net/anthropic`,鉴权头自动切换为 `Authorization: Bearer`,模型名用短形式 `claude-haiku-4-5`

papergames 内部环境通常已经设好 PaperHub 三件套环境变量,fetch.py 直接拿来用,无需手动改 config。

翻译规则(系统提示固化,详见 fetch.py 的 `TRANSLATE_SYSTEM_PROMPT`):

- 保留原文不译: Unreal Engine / UE5 / UEFN / Niagara / Lumen / Nanite / MegaLights / Chaos / Substrate / MetaHuman / Cascadeur 等技术名词与产品名
- 保留原文不译: 游戏名 / 工作室名 / 品牌名
- 保留原文不译: `| Inside Unreal` / `| Game Profile` / `| UEFN Build Along` 等系列标识

无 key 时翻译步骤跳过,中文标题留空,不影响其他流程。翻译失败也不阻塞写入和推送。

## 何时使用

- 用户要刷新 / 检查 UE 频道有没有新视频
- 用户挂的定时任务自动触发

## 不该使用的场景

- 用户问 UE 引擎技术问题
- 用户要做视频笔记 / 摘要(那是 video-to-notes 的事,本 skill 只管清单)

## 错误处理

| 现象 | 退出码 | 处理 |
|---|---|---|
| 配置文件缺失 | 2 | 提示用户去 `%USERPROFILE%\.config\ue-video-feed\` 创建 |
| YouTube API 配额用尽 | 3 | 明日 UTC 0 点重置,告诉用户改天再试 |
| Base 写入失败 | 0(部分成功)| 打印 stderr,不阻塞推送 |
| 私聊发送失败 | 0(数据已入库)| 打印 stderr |
