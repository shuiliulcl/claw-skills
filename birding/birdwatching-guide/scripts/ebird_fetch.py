#!/usr/bin/env python3
"""eBird API 2.0 拉取脚本 —— 观鸟攻略 skill 的 eBird 子 Agent 专用。

从环境变量 EBIRD_API_KEY 读取 key（申请见 references/ebird-api.md）。
输出精简 JSON 到 stdout，供子 Agent 消化成摘要。

用法:
  python ebird_fetch.py obs    --lat 39.9 --lng 116.4 --dist 25 [--back 7]
  python ebird_fetch.py notable --lat 39.9 --lng 116.4 --dist 25 [--back 7]
  python ebird_fetch.py hotspots --lat 39.9 --lng 116.4 --dist 25

子命令:
  obs       附近近期观测（geo/recent）
  notable   附近近期罕见/高光鸟种（geo/recent/notable）
  hotspots  附近热点（ref/hotspot/geo）

所有距离单位为公里，eBird 最大 50；back=回溯天数，最大 30。
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

import birdwatch_config as cfg

# Windows 控制台默认非 UTF-8，强制 stdout/stderr 用 UTF-8，避免中文鸟名/地名乱码
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

BASE = "https://api.ebird.org/v2"


def call(path, params, key):
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"x-ebirdapitoken": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"eBird HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}\n")
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"eBird 请求失败: {e}\n")
        sys.exit(2)


def slim_obs(rows):
    """只保留攻略需要的字段，去掉冗余。"""
    out = []
    for o in rows:
        out.append({
            "comName": o.get("comName"),       # 中文/英文俗名
            "sciName": o.get("sciName"),
            "locName": o.get("locName"),        # 观测地点
            "obsDt": o.get("obsDt"),            # 观测时间
            "howMany": o.get("howMany"),        # 数量
            "lat": o.get("lat"),
            "lng": o.get("lng"),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["obs", "notable", "hotspots"])
    ap.add_argument("--lat", required=True)
    ap.add_argument("--lng", required=True)
    ap.add_argument("--dist", default="25", help="半径公里，最大 50")
    ap.add_argument("--back", default="7", help="回溯天数，最大 30")
    args = ap.parse_args()

    key = cfg.get("ebird_api_key", env="EBIRD_API_KEY")
    if not key:
        sys.stderr.write("缺少 ebird_api_key（config.json 或 env EBIRD_API_KEY），申请见 references/ebird-api.md\n")
        sys.exit(1)

    if args.cmd == "obs":
        data = call("/data/obs/geo/recent",
                    {"lat": args.lat, "lng": args.lng, "dist": args.dist, "back": args.back},
                    key)
        print(json.dumps(slim_obs(data), ensure_ascii=False, indent=2))
    elif args.cmd == "notable":
        data = call("/data/obs/geo/recent/notable",
                    {"lat": args.lat, "lng": args.lng, "dist": args.dist, "back": args.back, "detail": "full"},
                    key)
        print(json.dumps(slim_obs(data), ensure_ascii=False, indent=2))
    elif args.cmd == "hotspots":
        data = call("/ref/hotspot/geo",
                    {"lat": args.lat, "lng": args.lng, "dist": args.dist, "fmt": "json"},
                    key)
        out = [{
            "locId": h.get("locId"),
            "locName": h.get("locName"),
            "numSpeciesAllTime": h.get("numSpeciesAllTime"),  # 历史累计种数，越高越值得去
            "lat": h.get("lat"),
            "lng": h.get("lng"),
        } for h in data]
        out.sort(key=lambda x: x.get("numSpeciesAllTime") or 0, reverse=True)
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
