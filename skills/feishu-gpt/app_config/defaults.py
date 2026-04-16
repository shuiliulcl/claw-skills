from dataclasses import dataclass, field


@dataclass(frozen=True)
class AppSettings:
    app_id: str = ""
    app_secret: str = ""
    notify_chat_id: str = ""
    notify_open_id: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-5"
    openai_timeout: int = 600
    agents_path: str = ""
    feishu_cli_enabled: bool = False
    feishu_cli_bin: str = "lark-cli"
    feishu_cli_as: str = ""
    feishu_cli_timeout: int = 120
    feishu_cli_extra_args: list[str] = field(default_factory=list)
