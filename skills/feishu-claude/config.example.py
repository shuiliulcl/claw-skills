# 复制此文件为 config.py 并填写真实值
# Copy this file to config.py and fill in your values

APP_ID     = "cli_xxxxxxxxxxxxxxxx"   # 飞书开放平台 → 凭证与基础信息
APP_SECRET = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
WORK_DIR   = r"C:\your\project"       # Claude Code 工作目录，留空则使用用户主目录

# 机器人启动时发送上线通知的会话 ID，留空则不发
NOTIFY_CHAT_ID = ""

# Claude 调用超时秒数（复杂任务如代码分析可能需要较长时间）
CLAUDE_TIMEOUT = 600

# 跳过 Claude Code 的交互权限询问（bot 模式下无法在终端审批，建议开启）
CLAUDE_SKIP_PERMISSIONS = True
