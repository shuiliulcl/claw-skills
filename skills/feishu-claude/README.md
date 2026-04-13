# 飞书 × Claude Code 机器人

通过飞书 WebSocket 长连接实时接收消息，调用本地 Claude Code CLI 生成回复。**无需公网 IP，开箱即用。**

## 功能特性

- **多轮对话**：按会话隔离上下文，同一会话内保持连贯对话
- **自动摘要压缩**：历史过长时自动压缩为摘要，不丢断上下文
- **思考中表情**：收到消息立即在原消息上添加 🤔 表情，回复后自动移除
- **Markdown 渲染**：回复以飞书卡片 2.0 呈现，支持标题、代码块、加粗、列表等完整 Markdown
- **回复串**：在线程中回复时归入消息串，普通消息则回复到会话
- **长消息分段**：超过 4000 字符自动拆分，带页码发送
- **线程安全去重**：防止飞书重推事件导致的重复回复
- **管理指令**：`/help` `/clear` `/history` `/cd <路径>`
- **引用消息识别**：自动将引用内容注入上下文
- **启动通知**：bot 上线时向指定会话发送通知

## 目录结构

```
feishu-claude/
├── config.py          # 配置（不上传，含密钥）
├── config.example.py  # 配置模板（复制为 config.py 后填写）
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
pip install lark-oapi
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
WORK_DIR                = r"C:\your\project"  # Claude Code 工作目录，留空使用用户主目录
NOTIFY_CHAT_ID          = ""                  # 启动通知会话 ID，留空不发
CLAUDE_TIMEOUT          = 600                 # 超时秒数（分析大型代码库建议 300-600）
CLAUDE_SKIP_PERMISSIONS = True                # 跳过权限询问（bot 模式下必须开启）
```

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
| `/history` | 查看上下文保留轮数和当前工作目录 |
| `/cd <路径>` | 切换当前会话的 Claude 工作目录 |

## 关键参数

| 参数 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| `CLAUDE_TIMEOUT` | config.py | 600 | Claude CLI 调用超时秒数 |
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

**Q: 响应超时**  
A: 默认等待 600 秒。分析大型代码库时可能仍不够，在 `config.py` 中调大 `CLAUDE_TIMEOUT`。

**Q: Markdown 未正确渲染**  
A: 使用飞书卡片 2.0 格式（`schema: "2.0"`），已支持标题、代码块、列表等完整语法。

**Q: 重启脚本双击闪退**  
A: 直接双击 `restart.vbs`，不要双击 `restart.bat`。`.bat` 文件在某些 Windows 配置下会闪退，`.vbs` 会显式打开持久窗口。
