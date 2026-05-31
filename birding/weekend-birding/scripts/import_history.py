#!/usr/bin/env python3
"""把中国观鸟记录中心的历史出行导入 Obsidian，生成 trip 笔记（双链到物种）。

只读你的报告（activity/search + record/taxon），只在 vault 的「观鸟/trips/」下新建笔记。
已存在同名 trip 笔记默认跳过（不覆盖你的手写内容）。

环境变量：BIRDREPORT_TOKEN、BIRDWATCH_VAULT（默认 ~/ObsidianVault）
用法：
  python import_history.py [--start 2014-01-01] [--end 今天] [--overwrite]
"""
import argparse
import base64
import json
import os
import re
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

_AES_KEY = b"C8EB5514AF5ADDB94B2207B08C66601C"
_AES_IV = b"55DD79C6F04E1A67"
BASE = "https://api.birdreport.cn"


def api(path, body):
    token = cfg.get("birdreport.token", env="BIRDREPORT_TOKEN")
    if not token:
        sys.exit("缺少 birdreport.token（config.json 或 env）；可用 grab_token.py 获取")
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Auth-Token": token,
                 "Origin": "https://www.birdreport.cn", "Referer": "https://www.birdreport.cn/",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
        method="POST")
    try:
        p = json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"{path} HTTP {e.code}（401/403 多为 token 失效）")
    if p.get("code") not in (0, "0"):
        sys.exit(f"{path} 业务错误: {json.dumps(p, ensure_ascii=False)[:160]}")
    data = p.get("data")
    if isinstance(data, str) and data:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        return json.loads(unpad(AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(base64.b64decode(data)), 16).decode("utf-8"))
    return data or []


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "-", name).strip()


def trip_note(act, species):
    date = (act.get("start_time") or "")[:10]
    note = [
        "---", "type: 观鸟出行", f"date: {date}",
        f"地点: {act.get('point_name')}", f"point_id: {act.get('point_id')}",
        f"省市: {act.get('province_name') or ''}/{act.get('district_name') or ''}",
        f"鸟种数: {act.get('taxon_count') or len(species)}",
        f"serial_id: {act.get('serial_id') or ''}",
        "tags: [观鸟/出行]", "来源: 中国观鸟记录中心", "---", "",
        f"# {date} {act.get('point_name')}", "",
        f"时段：{act.get('start_time') or ''} → {act.get('end_time') or ''}", "",
        "## 鸟种记录", "",
    ]
    for name, cnt in species:
        note.append(f"- [[{name}]] ×{cnt}")
    note.append("")
    return "\n".join(note)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=None)
    ap.add_argument("--start", default="2014-01-01")
    ap.add_argument("--end", default=time.strftime("%Y-%m-%d"))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    if not args.vault and not cfg.flag("obsidian.enabled"):
        sys.exit("Obsidian 集成未启用（config.json obsidian.enabled=false）。启用后再导入，或用 --vault 指定。")
    vault = args.vault or cfg.get_path("obsidian.vault_path", env="BIRDWATCH_VAULT")
    if not vault or not os.path.isdir(vault):
        sys.exit(f"找不到 vault：{vault}")
    args.vault = vault
    trips_dir = os.path.join(vault, "观鸟", "trips")
    os.makedirs(trips_dir, exist_ok=True)

    # 拉全部出行（activity/search 按日期过滤，省市留空取全部本人报告）
    acts = []
    for page in range(1, 50):
        rows = api("/member/system/activity/search",
                   {"page": page, "limit": 100, "province": "", "city": "", "district": "",
                    "startTime": args.start, "endTime": args.end})
        if not rows:
            break
        acts.extend(rows)
        if len(rows) < 100:
            break
        time.sleep(args.delay)
    print(f"共获取出行 {len(acts)} 次，开始生成 trip 笔记…")

    created, skipped = 0, 0
    for a in acts:
        date = (a.get("start_time") or "")[:10]
        fname = safe_filename(f"{date} {a.get('point_name')}") + ".md"
        path = os.path.join(trips_dir, fname)
        if os.path.exists(path) and not args.overwrite:
            skipped += 1
            continue
        taxa = api("/member/system/record/taxon",
                   {"page": 1, "limit": 1500, "activity_id": a.get("id")}) or []
        species = [(t.get("taxon_name"), t.get("taxon_count")) for t in taxa if t.get("taxon_name")]
        with open(path, "w", encoding="utf-8") as f:
            f.write(trip_note(a, species))
        created += 1
        print(f"  ✓ {fname}  ({len(species)} 种)")
        time.sleep(args.delay)

    print(f"\n完成：新建 {created} 篇 trip 笔记，跳过(已存在) {skipped}，目录 {trips_dir}")


if __name__ == "__main__":
    main()
