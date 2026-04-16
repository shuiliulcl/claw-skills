# 飞书 × ChatGPT 机器人

通过飞书 WebSocket 长连接实时接收消息，调用 OpenAI API 生成回复。**无需公网 IP，开箱即用。**

## 功能特性

- **多轮对话**：按会话隔离上下文，同一会话内保持连贯对话
- **自动摘要压缩**：历史过长时自动压缩为摘要，不丢断上下文
- **思考中表情**：收到消息立即在原消息上添加 🤔 表情，回复后自动移除
- **普通文本回复**：默认发送接近日常聊天的文本消息，不再使用 Markdown 卡片
- **回复串**：在线程中回复时归入消息串，普通消息则回复到会话
- **长消息分段**：超过 4000 字符自动拆分，带页码发送
- **线程安全去重**：防止飞书重推事件导致的重复回复
- **工作区编辑器**：可在工作区内列目录、读文件、写文件、追加文件、删文件、建目录
- **记忆写入**：支持按 `AGENTS.md` 指令将记忆写入工作区下的 `memory/` 目录
- **飞书 CLI 集成**：可通过官方 `lark-cli` 直接操作飞书消息、文档、日历、任务等能力
- **定时任务**：支持周期任务、每日任务、一次性任务、暂停恢复和工作时间窗口
- **心跳自检**：后台定时检查 Agent 线程、飞书长连接和 HEARTBEAT 轮询结果
- **管理指令**：`/help` `/clear` `/history` 和一组 `/task-*` 指令
- **引用消息识别**：自动将引用内容注入上下文
- **启动通知**：bot 上线时可向指定会话或指定用户发送通知

## 目录结构

```
feishu-gpt/
├── app_config/        # 配置层（local.py / local.example.py）
├── bot_runtime/       # 程序运行时模块
├── runtime_data/      # 运行时数据（pid / tasks）
├── agents.example.md  # AGENTS 模板
├── AGENTS.md          # 默认工作区初始化指令
├── bot.py             # 极薄入口
├── restart.vbs
├── restart.bat
├── start.ps1
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install lark-oapi openai
```

如需启用飞书 CLI 工具，还需要先安装：

```bash
npm install -g @larksuite/cli
lark-cli config init
lark-cli auth login --recommend
```

### 2. 配置

复制模板并填写：

```bash
cp app_config/local.example.py app_config/local.py
```

编辑 `app_config/local.py`：

```python
APP_ID                  = "cli_xxxxxxxx"      # 飞书开放平台 → 凭证与基础信息
APP_SECRET              = "xxxxxxxxxxxxxxxx"
NOTIFY_CHAT_ID          = ""                  # 启动通知会话 ID
NOTIFY_OPEN_ID          = ""                  # 启动通知用户 open_id
OPENAI_API_KEY          = "sk-xxxxxxxx"
OPENAI_BASE_URL         = "https://your-openai-compatible-host/v1"  # 兼容 OpenAI 的服务地址
OPENAI_MODEL            = "gpt-5"
OPENAI_TIMEOUT          = 600
AGENTS_PATH             = ""                  # Agent 工作区目录，默认读取其中的 AGENTS.md

FEISHU_CLI_ENABLED      = True
FEISHU_CLI_BIN          = "lark-cli"
FEISHU_CLI_TIMEOUT      = 120
FEISHU_CLI_EXTRA_ARGS   = []
```

当前代码按兼容 OpenAI 的 `POST /chat/completions` 调用接口，SDK 会自动带上：

- `Authorization: Bearer {OPENAI_API_KEY}`
- `Content-Type: application/json`

如需接入飞书 CLI：

- 将 `FEISHU_CLI_ENABLED` 设为 `True`
- 先执行 `lark-cli config init` 完成应用配置
- 再执行 `lark-cli auth login --recommend` 完成用户授权
- 当前实现会给 Agent 提供通用 Shell 工具，调用飞书能力时直接执行 `lark-cli`

如需自定义 Agent 初始化指令：

```bash
cp Agents.example.md <你的工作区>/AGENTS.md
```

然后在 `app_config/local.py` 中把 `AGENTS_PATH` 指到这个工作区目录。机器人会读取该目录下的 `AGENTS.md`，并把里面的内容整体作为初始化指令。该文件中提到的文件名和相对路径，都按这个工作区解析。

### 3. 飞书开放平台配置

1. 创建应用，开启**机器人**能力
2. 订阅事件：`im.message.receive_v1`（接收消息）
3. 开通权限：
   - `im:message`（发送消息）
   - `im:message:send_as_bot`
   - `im:message:retrieve_for_bot`（读取引用消息内容）
   - `im:message.reaction:write`（添加/移除表情回复）

### 4. 启动

```bash
python bot.py
```

默认会同时启动：

- 飞书机器人
- 本地对话命令行

Windows 下也可以直接运行：

```powershell
.\start.ps1
```

本地对话模式：

```bash
python bot.py --local-chat
```

或双击 `restart.vbs`（Windows，自动关闭旧进程并重启）。

## 一键重启

双击 `restart.vbs` 即可：

1. 读取 `runtime_data/bot.pid`，精准杀掉旧进程
2. 启动新的 bot 进程

> `restart.vbs` 作为入口，显式以 `cmd /k` 打开窗口，避免 Windows 闪退问题。

## 管理指令

| 指令 | 说明 |
|------|------|
| `/help` | 显示可用指令列表 |
| `/clear` | 清除当前会话的对话历史 |
| `/history` | 查看上下文保留轮数、当前模型和工作区 |
| `/task-add <分钟> <任务内容>` | 创建按分钟循环的定时任务 |
| `/task-add-daily <HH:MM> <任务内容>` | 创建每日任务 |
| `/task-add-once <YYYY-MM-DD> <HH:MM> <任务内容>` | 创建一次性任务 |
| `/task-list` | 查看当前定时任务 |
| `/task-del <task_id>` | 删除定时任务 |
| `/task-run <task_id>` | 立即执行一次定时任务 |
| `/task-pause <task_id>` | 暂停定时任务 |
| `/task-resume <task_id>` | 恢复定时任务 |
| `/task-window <task_id> <days> <HH:MM-HH:MM>` | 设置工作时间窗口 |

## 关键参数

| 参数 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `NOTIFY_CHAT_ID` | app_config/local.py | 空 | 启动时向指定会话发送上线通知 |
| `NOTIFY_OPEN_ID` | app_config/local.py | 空 | 启动时向指定用户 open_id 发送上线通知 |
| `OPENAI_MODEL` | app_config/local.py | gpt-5 | 调用的 OpenAI 模型 |
| `OPENAI_TIMEOUT` | app_config/local.py | 600 | OpenAI API 调用超时秒数 |
| `AGENTS_PATH` | app_config/local.py | 空 | Agent 工作区目录，程序会读取其中的 `AGENTS.md` |
| `FEISHU_CLI_ENABLED` | app_config/local.py | False | 是否启用 `lark-cli` |
| `FEISHU_CLI_BIN` | app_config/local.py | lark-cli | CLI 可执行文件名或绝对路径 |
| `FEISHU_CLI_AS` | app_config/local.py | 空 | 预留的 CLI 身份配置 |
| `FEISHU_CLI_TIMEOUT` | app_config/local.py | 120 | 单次 CLI 调用超时秒数 |
| `FEISHU_CLI_EXTRA_ARGS` | app_config/local.py | 空列表 | 默认附加参数 |
| `runtime_data/` | 运行目录 | - | 存放 `bot.pid` 和 `scheduled_tasks.json` |

## 常见问题

**Q: 消息重复发送**  
A: 已通过原子去重 + 后台线程解决。若仍出现，检查网络稳定性。

**Q: 思考中表情添加失败**  
A: 需在飞书开放平台开通 `im:message.reaction:write` 权限。

**Q: 引用内容未被识别**  
A: 需开通 `im:message:retrieve_for_bot` 权限；缺少权限时正常回复不受影响。

**Q: OpenAI 认证失败**  
A: 检查 `app_config/local.py` 中的 `OPENAI_API_KEY` 是否正确，项目余额和模型权限是否正常。

**Q: 飞书 CLI 不可用 / Agent 调不了飞书工具？**  
A: 先确认本机已安装 Node.js 和 `lark-cli`，再执行 `lark-cli auth status` 与 `lark-cli doctor` 检查登录和配置状态。

**Q: 如何在本地直接和 Agent 对话？**  
A: 运行 `python bot.py` 会同时启动飞书机器人和本地对话；如果只想开本地对话，运行 `python bot.py --local-chat`。

**Q: 现在可以直接修改本地文件吗？**  
A: 可以。Agent 已支持工作区内的文件工具调用，能按要求读写、创建、删除文件，并可将记忆写入 `memory/` 目录。

**Q: 响应超时**  
A: 默认等待 600 秒。复杂问题可能仍不够，在 `app_config/local.py` 中调大 `OPENAI_TIMEOUT`。

**Q: 为什么现在不是 Markdown 卡片了？**  
A: 当前默认发送普通文本消息，目的是让聊天体验更自然；如需重新做卡片层，可以在 `bot_runtime/messaging.py` 扩展。

**Q: 重启脚本双击闪退**  
A: 直接双击 `restart.vbs`，不要双击 `restart.bat`。`.bat` 文件在某些 Windows 配置下会闪退，`.vbs` 会显式打开持久窗口。
