#!/usr/bin/env python3
"""拉取并缓存「个人人生鸟单」—— 来自中国观鸟记录中心(birdreport.cn)的总鸟种信息。

接口 /member/system/record/searchTaxon 直接返回当前 token 用户的全部已记录鸟种
（含 taxon_id / 最早记录时间 / 报告次数 / 科目）。缓存到共享目录供攻略"可加新/已解锁"比对用。

环境变量：BIRDREPORT_TOKEN（会过期，失效重新复制）

用法：
  python lifelist.py            # 拉取并写入 ~/.birdwatch/lifelist.json
  python lifelist.py --print    # 顺带打印摘要
"""
import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error

import birdwatch_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

_AES_KEY = b"C8EB5514AF5ADDB94B2207B08C66601C"
_AES_IV = b"55DD79C6F04E1A67"
URL = "https://api.birdreport.cn/member/system/record/searchTaxon"
OUT_DIR = os.path.join(os.path.expanduser("~"), ".birdwatch")
OUT = os.path.join(OUT_DIR, "lifelist.json")


def fetch():
    token = cfg.get("birdreport.token", env="BIRDREPORT_TOKEN")
    if not token:
        sys.exit("缺少 birdreport.token（config.json 或 env）；可用 grab_token.py 自动获取")
    req = urllib.request.Request(URL, data=json.dumps({"page": 1, "limit": 5000}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Auth-Token": token,
                 "Origin": "https://www.birdreport.cn", "Referer": "https://www.birdreport.cn/",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
        method="POST")
    try:
        p = json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}（401/403 多为 token 失效）")
    if p.get("code") not in (0, "0"):
        sys.exit(f"接口错误: {json.dumps(p, ensure_ascii=False)[:160]}")
    data = p.get("data")
    if isinstance(data, str):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        data = json.loads(unpad(AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(base64.b64decode(data)), 16).decode("utf-8"))
    return data or []


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", action="store_true", dest="show")
    args = ap.parse_args()

    rows = fetch()
    species = [{
        "taxon_id": r.get("taxon_id"), "name": r.get("taxon_name"), "latin": r.get("latinname"),
        "earliest": r.get("earlist_time"), "reports": r.get("report_d_num"),
        "family": r.get("taxonfamilyname"), "order": r.get("taxonordername"),
    } for r in rows]
    species.sort(key=lambda x: x["taxon_id"] or 0)
    os.makedirs(OUT_DIR, exist_ok=True)
    import time
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "total": len(species), "species": species}, f, ensure_ascii=False, indent=2)
    print(f"已缓存人生鸟单 {len(species)} 种 -> {OUT}")
    if args.show:
        for s in species[:12]:
            print(f"  {s['name']}  最早 {s['earliest']}  报告{s['reports']}次")
        print("  ...")


if __name__ == "__main__":
    main()
