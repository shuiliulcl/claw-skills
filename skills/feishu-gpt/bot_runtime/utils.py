import json
import time


def first_non_empty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def format_timestamp_ms(value) -> str:
    if value in (None, ""):
        return ""
    try:
        ts = int(value)
        if ts > 10**12:
            ts = ts / 1000.0
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return str(value)


def summarize_json_payload(payload) -> str:
    if isinstance(payload, dict):
        parts = []
        for key in sorted(payload.keys()):
            value = payload[key]
            if isinstance(value, (str, int, float, bool)) and str(value).strip():
                parts.append(f"{key}={value}")
            elif isinstance(value, list) and value:
                parts.append(f"{key}=[{len(value)}项]")
            elif isinstance(value, dict) and value:
                parts.append(f"{key}={{...}}")
        return "；".join(parts[:6])
    if isinstance(payload, list):
        return f"列表，共 {len(payload)} 项"
    if payload not in (None, ""):
        return str(payload)
    return ""


def compact_dict(data: dict) -> dict:
    compacted = {}
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        compacted[key] = value
    return compacted


def serialize_sdk_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        items = [serialize_sdk_value(item) for item in value]
        return [item for item in items if item is not None]
    if isinstance(value, dict):
        return compact_dict({k: serialize_sdk_value(v) for k, v in value.items()})

    result = {}
    for key, item in vars(value).items():
        if key.startswith("_"):
            continue
        serialized = serialize_sdk_value(item)
        if serialized is not None and serialized != {} and serialized != []:
            result[key] = serialized
    return result or None


def json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False)
