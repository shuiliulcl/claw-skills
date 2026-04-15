# 复制此文件为 config.py 并填写真实值
# Copy this file to config.py and fill in your values

APP_ID     = "cli_xxxxxxxxxxxxxxxx"   # 飞书开放平台 → 凭证与基础信息
APP_SECRET = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 机器人启动时发送上线通知的会话 ID，留空则不发
NOTIFY_CHAT_ID = ""
NOTIFY_OPEN_ID = ""                  # 启动时给指定用户发送上线通知，填用户 open_id

# OpenAI 配置
OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxx"
OPENAI_BASE_URL = ""  # 兼容 OpenAI 的服务地址
OPENAI_MODEL = "gpt-5"
OPENAI_TIMEOUT = 600
AGENTS_PATH = ""                      # Agent 工作区目录，默认读取其中的 AGENTS.md

# Feishu MCP 配置（远程 MCP）
FEISHU_MCP_ENABLED = False
# 远程 MCP 配置
FEISHU_MCP_URL = ""
FEISHU_MCP_HEADERS = {
    "AUTH_TYPE": "Bearer",
    "AUTH_TOKEN": "<your-mcp-token>",
}
