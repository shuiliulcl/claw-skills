"""和风天气配置加载器 —— ~/.qweather/config.json，环境变量作回退。

schema 是 flat 的，只装和风需要的 4 项 + 一个可选 amap_key：
    api_host / sub / kid / private_key_path / amap_key

amap_key 给 GeoAPI 备胎用——和风 GeoAPI 在默认项目安全策略下会 403，故
城市名→坐标走高德地理编码。amap_key 找不到时按顺序回退：
  ~/.qweather/config.json: amap_key
  ~/.amap/config.json: amap.key 或 key
  ~/.birdwatch/config.json: amap.key
  env AMAP_KEY

用法:
    import qweather_config as cfg
    host = cfg.get("api_host", env="QWEATHER_API_HOST")
    key_path = cfg.get_path("private_key_path", env="QWEATHER_PRIVATE_KEY",
                            default="C:/Users/banqiang/.qweather/ed25519-private.pem")
    amap = cfg.get_amap_key()
"""
import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".qweather")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def _load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _load():
    return _load_json(CONFIG_PATH)


def get(key, env=None, default=None):
    v = _load().get(key)
    if v not in (None, ""):
        return v
    if env and os.environ.get(env):
        return os.environ[env]
    return default


def get_path(key, env=None, default=None):
    v = get(key, env, default)
    return os.path.expanduser(v) if isinstance(v, str) and v else v


def get_amap_key():
    """高德地理编码 key——顺序：本 skill > ~/.amap > ~/.birdwatch > env。"""
    v = _load().get("amap_key")
    if v:
        return v
    amap_cfg = _load_json(os.path.join(os.path.expanduser("~"), ".amap", "config.json"))
    v = (amap_cfg.get("amap") or {}).get("key") or amap_cfg.get("key")
    if v:
        return v
    bw_cfg = _load_json(os.path.join(os.path.expanduser("~"), ".birdwatch", "config.json"))
    v = (bw_cfg.get("amap") or {}).get("key")
    if v:
        return v
    return os.environ.get("AMAP_KEY")
