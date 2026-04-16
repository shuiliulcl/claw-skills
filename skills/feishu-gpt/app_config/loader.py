from importlib import import_module

from .defaults import AppSettings

CONFIG_SOURCE = "defaults"


def _read_module(name: str):
    try:
        return import_module(name)
    except ModuleNotFoundError:
        return None


def _to_list(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in (value or []) if str(item).strip()]


def load_settings() -> AppSettings:
    global CONFIG_SOURCE

    module = _read_module("app_config.local")
    if module is not None:
        CONFIG_SOURCE = "app_config.local"
    else:
        return AppSettings()

    return AppSettings(
        app_id=str(getattr(module, "APP_ID", "") or ""),
        app_secret=str(getattr(module, "APP_SECRET", "") or ""),
        notify_chat_id=str(getattr(module, "NOTIFY_CHAT_ID", "") or ""),
        notify_open_id=str(getattr(module, "NOTIFY_OPEN_ID", "") or ""),
        openai_api_key=str(getattr(module, "OPENAI_API_KEY", "") or ""),
        openai_base_url=str(getattr(module, "OPENAI_BASE_URL", "") or ""),
        openai_model=str(getattr(module, "OPENAI_MODEL", "gpt-5") or "gpt-5"),
        openai_timeout=int(getattr(module, "OPENAI_TIMEOUT", 600) or 600),
        agents_path=str(getattr(module, "AGENTS_PATH", "") or ""),
        feishu_cli_enabled=bool(getattr(module, "FEISHU_CLI_ENABLED", False)),
        feishu_cli_bin=str(getattr(module, "FEISHU_CLI_BIN", "lark-cli") or "lark-cli"),
        feishu_cli_as=str(getattr(module, "FEISHU_CLI_AS", "") or ""),
        feishu_cli_timeout=int(getattr(module, "FEISHU_CLI_TIMEOUT", 120) or 120),
        feishu_cli_extra_args=_to_list(getattr(module, "FEISHU_CLI_EXTRA_ARGS", [])),
    )


settings = load_settings()
