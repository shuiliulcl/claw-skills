#!/usr/bin/env python3
"""和风天气 API 拉取脚本（JWT 认证）—— 观鸟攻略 skill 的天气子 Agent 专用。

和风 v7 推荐用 JWT（EdDSA/Ed25519）认证，本脚本用私钥本地签发短期 token。
API KEY 方式 2027 起限流，故不用。详见 references/qweather-api.md。

从环境变量读取:
  QWEATHER_API_HOST     你的专属 API Host，形如 abcd1234.re.qweatherapi.com
  QWEATHER_SUB          项目 ID（Project ID）
  QWEATHER_KID          凭证 ID（Credential ID，上传公钥后控制台给）
  QWEATHER_PRIVATE_KEY  Ed25519 私钥 PEM 文件路径
                        （默认 C:/Users/<user>/.qweather/ed25519-private.pem）

依赖 cryptography 库（pip install cryptography）。

用法:
  python qweather_fetch.py --lng 121.47 --lat 31.23

注意 location 参数顺序是「经度,纬度」（lng,lat），和很多 API 相反，别填反。
"""
import argparse
import base64
import gzip
import json
import os
import sys
import time
import urllib.request
import urllib.error

import birdwatch_config as cfg

# Windows 控制台默认非 UTF-8，强制 stdout/stderr 用 UTF-8，避免中文乱码
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DEFAULT_KEY_PATH = os.path.expanduser("~/.qweather/ed25519-private.pem")


def _b64url(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def make_jwt(sub: str, kid: str, key_path: str) -> str:
    """用 Ed25519 私钥签发和风要求的 JWT（最长 24h，这里取 15 分钟）。"""
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
    except ImportError:
        sys.stderr.write("缺少 cryptography 库，请先 pip install cryptography\n")
        sys.exit(1)

    with open(key_path, "rb") as f:
        priv = load_pem_private_key(f.read(), password=None)

    now = int(time.time())
    header = {"alg": "EdDSA", "kid": kid}
    payload = {"sub": sub, "iat": now - 30, "exp": now + 900}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + b"."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = priv.sign(signing_input)  # Ed25519 一步签名
    return (signing_input + b"." + _b64url(sig)).decode()


def call(host, token, lng, lat):
    loc = f"{lng},{lat}"  # 经度在前、纬度在后
    url = f"https://{host}/v7/weather/3d?location={loc}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            # 和风接口默认 gzip 压缩，按响应头解压
            if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"和风 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}\n")
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"和风请求失败: {e}\n")
        sys.exit(2)


def birding_hint(day):
    """根据降水/风力给一句观鸟建议。雨天鸟少且难拍，大风同理；晴和微风最佳。"""
    try:
        pop = float(day.get("precip", "0") or 0)
    except ValueError:
        pop = 0
    try:
        wind = int((day.get("windScaleDay", "0") or "0").split("-")[-1])
    except ValueError:
        wind = 0
    text = day.get("textDay", "")
    if pop > 0 or "雨" in text or "雪" in text:
        return "有降水，鸟类活动减少且不利拍摄，建议改期或选雨歇时段"
    if wind >= 5:
        return "风力较大，小型鸟躲风、林鸟难觅，优先背风林缘或水域"
    return "天气适宜，清晨与傍晚为观鸟黄金时段"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lng", required=True, help="经度")
    ap.add_argument("--lat", required=True, help="纬度")
    args = ap.parse_args()

    host = cfg.get("qweather.api_host", env="QWEATHER_API_HOST")
    sub = cfg.get("qweather.sub", env="QWEATHER_SUB")
    kid = cfg.get("qweather.kid", env="QWEATHER_KID")
    key_path = cfg.get_path("qweather.private_key_path", env="QWEATHER_PRIVATE_KEY", default=DEFAULT_KEY_PATH)
    missing = [n for n, v in [("qweather.api_host", host), ("qweather.sub", sub),
                              ("qweather.kid", kid)] if not v]
    if missing:
        sys.stderr.write(f"缺少环境变量 {', '.join(missing)}，申请见 references/qweather-api.md\n")
        sys.exit(1)
    if not os.path.exists(key_path):
        sys.stderr.write(f"找不到私钥文件 {key_path}（可用 QWEATHER_PRIVATE_KEY 指定路径）\n")
        sys.exit(1)

    token = make_jwt(sub, kid, key_path)
    data = call(host, token, args.lng, args.lat)
    if data.get("code") != "200":
        sys.stderr.write(f"和风返回错误 code={data.get('code')}（401/403 多为 sub/kid/私钥不匹配或 host 错误）\n")
        sys.exit(2)

    out = []
    for d in data.get("daily", []):
        out.append({
            "date": d.get("fxDate"),
            "textDay": d.get("textDay"),
            "tempMax": d.get("tempMax"),
            "tempMin": d.get("tempMin"),
            "precip": d.get("precip"),
            "windDirDay": d.get("windDirDay"),
            "windScaleDay": d.get("windScaleDay"),
            "sunrise": d.get("sunrise"),
            "sunset": d.get("sunset"),
            "birdingHint": birding_hint(d),
        })
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
