"""统一配置加载器 —— 单一来源 ~/.birdwatch/config.json，环境变量作回退。

把所有 key/路径集中到一个配置文件，便于多机部署：新机只需放一份 config.json。
env 回退保证旧的"环境变量"用法仍可用（平滑过渡）。

用法:
    import birdwatch_config as cfg
    key = cfg.get("ebird_api_key", env="EBIRD_API_KEY")
    host = cfg.get("qweather.api_host", env="QWEATHER_API_HOST")
    if cfg.flag("obsidian.enabled"): ...
    cfg.set_value("birdreport.token", new_token)   # 刷新 token 写回
"""
import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".birdwatch")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def _load():
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _dig(d, dotted):
    cur = d
    for k in dotted.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def get(dotted, env=None, default=None):
    """取配置项；config.json 优先，其次环境变量 env，再次 default。"""
    v = _dig(_load(), dotted)
    if v not in (None, ""):
        return v
    if env and os.environ.get(env):
        return os.environ[env]
    return default


def get_path(dotted, env=None, default=None):
    """取路径项并展开 ~。"""
    v = get(dotted, env, default)
    return os.path.expanduser(v) if isinstance(v, str) and v else v


def flag(dotted, default=False):
    """取布尔开关（用于可选功能 obsidian/ccconnect）。"""
    v = _dig(_load(), dotted)
    return bool(v) if v is not None else default


def set_value(dotted, value):
    """写回配置项（用于 grab_token 刷新 birdreport.token）。"""
    cfg = _load()
    cur = cfg
    parts = dotted.split(".")
    for k in parts[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[parts[-1]] = value
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
