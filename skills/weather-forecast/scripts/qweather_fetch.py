#!/usr/bin/env python3
"""和风天气 3 天预报（JWT 认证）—— 支持城市名 / 经纬度两种输入。

鉴权用 Ed25519 私钥本地签发 15 分钟 JWT（和风 v7 推荐方式，API KEY 2027 起限流故不用）。
配置见 references/qweather-api.md，集中在 ~/.qweather/config.json：
  api_host           你的专属 host，形如 abcd1234.re.qweatherapi.com
  sub                项目 ID
  kid                凭证 ID（上传公钥后控制台给）
  private_key_path   Ed25519 私钥 PEM 路径（默认 C:/Users/banqiang/.qweather/ed25519-private.pem）

依赖 cryptography（pip install cryptography）。

用法:
  python qweather_fetch.py --city 上海
  python qweather_fetch.py --lng 121.47 --lat 31.23

注意 location 参数顺序是「经度,纬度」（lng,lat），和很多 API 相反。脚本已处理，手动调用注意。
"""
import argparse
import base64
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

import qweather_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DEFAULT_KEY_PATH = "C:/Users/banqiang/.qweather/ed25519-private.pem"


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
    sig = priv.sign(signing_input)
    return (signing_input + b"." + _b64url(sig)).decode()


def _http_get_json(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"和风 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}\n")
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"和风请求失败: {e}\n")
        sys.exit(2)


def geo_lookup(name: str):
    """城市名 → 坐标。

    用高德地理编码 (`https://restapi.amap.com/v3/geocode/geo`)——和风 GeoAPI 在
    默认项目安全策略下会 403，且中文行政区名解析高德更稳。
    """
    amap_key = cfg.get_amap_key()
    if not amap_key:
        sys.stderr.write("没找到高德 key（用于解析城市名）。把 key 放进 ~/.amap/config.json "
                         "或 ~/.qweather/config.json 的 amap_key 字段，或直接传 --lng/--lat\n")
        sys.exit(1)
    q = urllib.parse.urlencode({"address": name, "key": amap_key})
    url = f"https://restapi.amap.com/v3/geocode/geo?{q}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"高德地理编码请求失败: {e}\n")
        sys.exit(2)
    if data.get("status") != "1" or not data.get("geocodes"):
        sys.stderr.write(f"高德解析失败：{data.get('info','no result')}（试试加省市前缀，"
                         f"如「上海市中山公园」而非「中山公园」）\n")
        sys.exit(2)
    g = data["geocodes"][0]
    lng, lat = g["location"].split(",")
    return {
        "name": g.get("formatted_address") or name,
        "adcode": g.get("adcode"),
        "city": g.get("city"),
        "province": g.get("province"),
        "lng": lng,
        "lat": lat,
    }


def weather_3d(host: str, token: str, lng: str, lat: str):
    loc = f"{lng},{lat}"  # 经度在前、纬度在后
    url = f"https://{host}/v7/weather/3d?location={loc}"
    data = _http_get_json(url, token)
    if data.get("code") != "200":
        sys.stderr.write(f"和风返回错误 code={data.get('code')}（401/403 多为 sub/kid/私钥不匹配或 host 错误）\n")
        sys.exit(2)
    out = []
    for d in data.get("daily", []):
        out.append({
            "date": d.get("fxDate"),
            "textDay": d.get("textDay"),
            "textNight": d.get("textNight"),
            "tempMax": d.get("tempMax"),
            "tempMin": d.get("tempMin"),
            "precip": d.get("precip"),
            "windDirDay": d.get("windDirDay"),
            "windScaleDay": d.get("windScaleDay"),
            "humidity": d.get("humidity"),
            "sunrise": d.get("sunrise"),
            "sunset": d.get("sunset"),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--city", help="城市名（中文/英文均可，如「上海」/「Shanghai」），调 GeoAPI 解析坐标")
    g.add_argument("--lng", help="经度（须与 --lat 同时给）")
    ap.add_argument("--lat", help="纬度（与 --lng 配对使用）")
    args = ap.parse_args()

    if args.lng and not args.lat:
        ap.error("--lng 必须和 --lat 一起给")

    host = cfg.get("api_host", env="QWEATHER_API_HOST")
    sub = cfg.get("sub", env="QWEATHER_SUB")
    kid = cfg.get("kid", env="QWEATHER_KID")
    key_path = cfg.get_path("private_key_path", env="QWEATHER_PRIVATE_KEY", default=DEFAULT_KEY_PATH)
    missing = [n for n, v in [("api_host", host), ("sub", sub), ("kid", kid)] if not v]
    if missing:
        sys.stderr.write(f"~/.qweather/config.json 缺少 {', '.join(missing)}，申请见 references/qweather-api.md\n")
        sys.exit(1)
    if not os.path.exists(key_path):
        sys.stderr.write(f"找不到私钥文件 {key_path}（可改 config.json 的 private_key_path）\n")
        sys.exit(1)

    token = make_jwt(sub, kid, key_path)

    resolved = None
    if args.city:
        resolved = geo_lookup(args.city)
        lng, lat = resolved["lng"], resolved["lat"]
    else:
        lng, lat = args.lng, args.lat

    daily = weather_3d(host, token, lng, lat)
    out = {"daily": daily}
    if resolved:
        out["resolved"] = resolved
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
