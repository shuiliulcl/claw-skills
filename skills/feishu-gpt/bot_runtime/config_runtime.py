import logging

import lark_oapi as lark
from openai import OpenAI

from app_config import CONFIG_SOURCE, settings

CONFIG_SOURCE_NAME = CONFIG_SOURCE

APP_ID = settings.app_id
APP_SECRET = settings.app_secret
NOTIFY_CHAT_ID = settings.notify_chat_id
NOTIFY_OPEN_ID = settings.notify_open_id
OPENAI_API_KEY = settings.openai_api_key
OPENAI_BASE_URL = settings.openai_base_url
OPENAI_MODEL = settings.openai_model
OPENAI_TIMEOUT = settings.openai_timeout
AGENTS_PATH = settings.agents_path

FEISHU_CLI_ENABLED = settings.feishu_cli_enabled
FEISHU_CLI_BIN = settings.feishu_cli_bin
FEISHU_CLI_AS = settings.feishu_cli_as
FEISHU_CLI_TIMEOUT = settings.feishu_cli_timeout
FEISHU_CLI_EXTRA_ARGS = [str(item) for item in settings.feishu_cli_extra_args if str(item).strip()]

MAX_IDS = 1000
MAX_HISTORY = 10
COMPRESS_AT = 8
KEEP_RECENT = 4
MSG_CHUNK_SIZE = 4000
MAX_TOOL_STEPS = 12
HEARTBEAT_INTERVAL_SECONDS = 1800
WS_RESTART_THRESHOLD = 2
HEARTBEAT_RESTART_THRESHOLD = 3
TASK_POLL_INTERVAL_SECONDS = 5


class _SuppressUnhandledEvents(logging.Filter):
    def filter(self, record):
        return "processor not found" not in record.getMessage()


_filter = _SuppressUnhandledEvents()
for _name in ["lark_oapi", "Lark", "", "root"]:
    logging.getLogger(_name).addFilter(_filter)

client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()
openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL or None,
    timeout=OPENAI_TIMEOUT,
)
