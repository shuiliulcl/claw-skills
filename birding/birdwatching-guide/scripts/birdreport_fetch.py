#!/usr/bin/env python3
"""中国观鸟记录中心（birdreport.cn）拉取脚本 —— 观鸟攻略 skill 的增强数据源。

【接入机制】站点 2024+ 改版后：请求为明文 JSON、需 X-Auth-Token 鉴权头、
响应 data 字段为 AES-256-CBC(base64) 加密。key/iv 见下（取自站点 aes.util.js）。
纯 Python 实现（pycryptodome），不再需要 Node/execjs/RSA。

【合规】仅供个人、低频观鸟规划使用，内置限速；数据版权属记录中心及记录者，
引用须注明来源。失败时不要硬刷、不要绕过校验，直接返回空让主 Agent 标注"未接入"。

环境变量:
  BIRDREPORT_TOKEN   登录 birdreport.cn 后从浏览器 DevTools 复制的 X-Auth-Token
                     （获取方法见 references/birdreport.md；网页重新登录会变）

用法:
  python birdreport_fetch.py --province 上海市 --city 上海市 --start 2026-05-15 --end 2026-05-29
可选: --district 区名  --pages N(默认2,每页100)  --delay 0.5  --with-taxon(逐报告取鸟种,慢)
输出: 精简 JSON —— 报告点位汇总（点名/区县/鸟种数/时间），可选鸟种聚合。
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

import birdwatch_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

# AES 常量（站点 aes.util.js 中混淆存储，已还原）
_AES_KEY = b"C8EB5514AF5ADDB94B2207B08C66601C"
_AES_IV = b"55DD79C6F04E1A67"

BASE = "https://api.birdreport.cn"
SEARCH_URL = BASE + "/member/system/activity/search"
# 鸟种明细接口：POST + body {activity_id}，返回该活动下的全部鸟种（AES 加密 data）。
TAXON_URL = BASE + "/member/system/record/search"


def _headers(token):
    return {
        "Content-Type": "application/json",
        "X-Auth-Token": token,
        "Origin": "https://www.birdreport.cn",
        "Referer": "https://www.birdreport.cn/",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    }


def _decrypt(b64text):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    ct = base64.b64decode(b64text)
    return unpad(AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(ct), 16).decode("utf-8")


def post(url, body, token, delay):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=_headers(token), method="POST")
    time.sleep(delay)
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"birdreport HTTP {e.code}（401/403 多为 token 失效，重新登录复制）\n")
        return None
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"birdreport 请求失败: {e}\n")
        return None
    if payload.get("code") != 0:
        sys.stderr.write(f"birdreport 业务错误: {json.dumps(payload, ensure_ascii=False)[:160]}\n")
        return None
    data = payload.get("data")
    if not data:
        return []
    try:
        return json.loads(_decrypt(data))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"birdreport 解密失败: {e}\n")
        return None


def search(province, city, district, start, end, pages, delay, token):
    out = []
    for page in range(1, pages + 1):
        body = {"page": page, "limit": 100, "province": province, "city": city,
                "district": district, "startTime": start, "endTime": end}
        rows = post(SEARCH_URL, body, token, delay)
        if not rows:
            break
        out.extend(rows)
        if len(rows) < 100:
            break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--province", default="")
    ap.add_argument("--city", default="")
    ap.add_argument("--district", default="")
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--with-taxon", action="store_true", help="逐报告抓鸟种(慢,礼貌限速)")
    ap.add_argument("--max-taxon", type=int, default=15, help="最多抓几份报告的鸟种")
    args = ap.parse_args()

    token = cfg.get("birdreport.token", env="BIRDREPORT_TOKEN")
    if not token:
        sys.stderr.write("缺少 birdreport.token（config.json 或 env），获取见 grab_token.py\n")
        print(json.dumps({"checklists": 0, "note": "未配置 token，未接入"}, ensure_ascii=False))
        return

    checklists = search(args.province, args.city, args.district,
                        args.start, args.end, args.pages, args.delay, token)
    if not checklists:
        print(json.dumps({"checklists": 0, "note": "未获取到记录或接口失败"}, ensure_ascii=False))
        return

    points = [{
        "point": c.get("point_name"), "district": c.get("district_name"),
        "taxon_count": c.get("taxon_count"), "start_time": c.get("start_time"),
        "serial_id": c.get("serial_id"), "id": c.get("id"),
    } for c in checklists]

    result = {
        "source": "中国观鸟记录中心 birdreport.cn",
        "checklists": len(checklists),
        "points": points[:30],
    }

    if args.with_taxon:
        species = {}
        for c in checklists[: args.max_taxon]:
            taxa = post(TAXON_URL, {"page": 1, "limit": 1500, "activity_id": c.get("id")},
                        token, args.delay)
            for t in (taxa or []):
                name = t.get("taxon_name") or t.get("taxonName")
                if name:
                    s = species.setdefault(name, {"comName": name,
                                                  "sciName": t.get("latinname") or t.get("latinName"),
                                                  "count": 0})
                    s["count"] += 1
        result["species_total"] = len(species)
        result["species"] = sorted(species.values(), key=lambda x: x["count"], reverse=True)
        if not species:
            result["taxon_note"] = "鸟种明细未取到（TAXON_URL 路径可能需更新，见 references/birdreport.md）"

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
