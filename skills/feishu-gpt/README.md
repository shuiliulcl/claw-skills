# 飞书 × ChatGPT 机器人

通过飞书 WebSocket 长连接实时接收消息，调用 OpenAI API 生成回复。**无需公网 IP，开箱即用。**

## 功能特性

- **多轮对话**：按会话隔离上下文，同一会话内保持连贯对话
- **自动摘要压缩**：历史过长时自动压缩为摘要，不丢断上下文
- **思考中表情**：收到消息立即在原消息上添加 🤔 表情，回复后自动移除
- **Markdown 渲染**：回复以飞书卡片 2.0 呈现，支持标题、代码块、加粗、列表等完整 Markdown
- **回复串**：在线程中回复时归入消息串，普通消息则回复到会话
- **长消息分段**：超过 4000 字符自动拆分，带页码发送
- **线程安全去重**：防止飞书重推事件导致的重复回复
- **工作区编辑器**：可在工作区内列目录、读文件、写文件、追加文件、删文件、建目录
- **记忆写入**：支持按 `AGENTS.md` 指令将记忆写入工作区下的 `memory/` 目录
- **飞书 MCP 桥接**：可通过远程 MCP 服务与 Header 鉴权接入飞书文档能力
- **管理指令**：`/help` `/clear` `/history`
- **引用消息识别**：自动将引用内容注入上下文
- **启动通知**：bot 上线时可向指定会话或指定用户发送通知

## 目录结构

```
feishu-claude/
├── config.py          # 配置（不上传，含密钥）
├── config.example.py  # 配置模板（复制为 config.py 后填写）
├── Agents.example.md  # AGENTS 模板（复制到工作区后命名为 AGENTS.md）
├── AGENTS.md          # 默认工作区中的初始化指令文件
├── bot.py             # 主程序
├── restart.vbs        # 一键重启入口（双击运行）
├── restart.bat        # 重启逻辑（由 restart.vbs 调用）
├── start.ps1          # 首次启动脚本（含环境检查）
├── .gitignore
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install lark-oapi openai
```

### 2. 配置

复制模板并填写：

```bash
cp config.example.py config.py
```

编辑 `config.py`：

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

FEISHU_MCP_ENABLED      = False
FEISHU_MCP_URL          = "https://your-mcp-server.example.com/mcp"
FEISHU_MCP_HEADERS      = {
    "AUTH_TYPE": "Bearer",
    "AUTH_TOKEN": "<your-mcp-token>",
}
```

当前代码按兼容 OpenAI 的 `POST /chat/completions` 调用接口，SDK 会自动带上：

- `Authorization: Bearer {OPENAI_API_KEY}`
- `Content-Type: application/json`

如需接入远程飞书 MCP：

- 将 `FEISHU_MCP_ENABLED` 设为 `True`
- `FEISHU_MCP_URL` 配成你的远程 MCP 地址
- `FEISHU_MCP_HEADERS` 里按文档填写：
  - `AUTH_TYPE: <你的鉴权类型>`
  - `AUTH_TOKEN: <你的访问令牌>`
- 当前实现会通过远程 MCP 动态获取可用工具，并合并进 Agent 的工具集

如需自定义 Agent 初始化指令：

```bash
cp Agents.example.md <你的工作区>/AGENTS.md
```

然后在 `config.py` 中把 `AGENTS_PATH` 指到这个工作区目录。机器人会读取该目录下的 `AGENTS.md`，并把里面的内容整体作为初始化指令。该文件中提到的文件名和相对路径，都按这个工作区解析。

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

本地对话模式：

```bash
python bot.py --local-chat
```

或双击 `restart.vbs`（Windows，自动关闭旧进程并重启）。

## 一键重启

双击 `restart.vbs` 即可：

1. 读取 `bot.pid`，精准杀掉旧进程
2. 启动新的 bot 进程

> `restart.vbs` 作为入口，显式以 `cmd /k` 打开窗口，避免 Windows 闪退问题。

## 管理指令

| 指令 | 说明 |
|------|------|
| `/help` | 显示可用指令列表 |
| `/clear` | 清除当前会话的对话历史 |
| `/history` | 查看上下文保留轮数、当前模型和工作区 |

## 关键参数

| 参数 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `NOTIFY_CHAT_ID` | config.py | 空 | 启动时向指定会话发送上线通知 |
| `NOTIFY_OPEN_ID` | config.py | 空 | 启动时向指定用户 open_id 发送上线通知 |
| `OPENAI_MODEL` | config.py | gpt-5 | 调用的 OpenAI 模型 |
| `OPENAI_TIMEOUT` | config.py | 600 | OpenAI API 调用超时秒数 |
| `AGENTS_PATH` | config.py | 空 | Agent 工作区目录，程序会读取其中的 `AGENTS.md` |
| `FEISHU_MCP_ENABLED` | config.py | False | 是否启用飞书 MCP 桥接 |
| `FEISHU_MCP_URL` | config.py | 见示例 | 远程 MCP 服务地址 |
| `FEISHU_MCP_HEADERS` | config.py | 见示例 | 远程 MCP 请求头，包含 `AUTH_TYPE` 和 `AUTH_TOKEN` |
| `MAX_HISTORY` | bot.py | 10 | 完整保留的最大对话轮数 |
| `COMPRESS_AT` | bot.py | 8 | 触发摘要压缩的轮数阈值 |
| `KEEP_RECENT` | bot.py | 4 | 压缩后保留的最近轮数 |
| `MAX_IDS` | bot.py | 1000 | 去重集合上限 |
| `MSG_CHUNK_SIZE` | bot.py | 4000 | 单条消息字符上限 |

## 常见问题

**Q: 消息重复发送**  
A: 已通过原子去重 + 后台线程解决。若仍出现，检查网络稳定性。

**Q: 思考中表情添加失败**  
A: 需在飞书开放平台开通 `im:message.reaction:write` 权限。

**Q: 引用内容未被识别**  
A: 需开通 `im:message:retrieve_for_bot` 权限；缺少权限时正常回复不受影响。

**Q: OpenAI 认证失败**  
A: 检查 `config.py` 中的 `OPENAI_API_KEY` 是否正确，项目余额和模型权限是否正常。

**Q: 如何在本地直接和 Agent 对话？**  
A: 运行 `python bot.py` 会同时启动飞书机器人和本地对话；如果只想开本地对话，运行 `python bot.py --local-chat`。

**Q: 现在可以直接修改本地文件吗？**  
A: 可以。Agent 已支持工作区内的文件工具调用，能按要求读写、创建、删除文件，并可将记忆写入 `memory/` 目录。

**Q: 响应超时**  
A: 默认等待 600 秒。复杂问题可能仍不够，在 `config.py` 中调大 `OPENAI_TIMEOUT`。

**Q: Markdown 未正确渲染**  
A: 使用飞书卡片 2.0 格式（`schema: "2.0"`），已支持标题、代码块、列表等完整语法。

**Q: 重启脚本双击闪退**  
A: 直接双击 `restart.vbs`，不要双击 `restart.bat`。`.bat` 文件在某些 Windows 配置下会闪退，`.vbs` 会显式打开持久窗口。
