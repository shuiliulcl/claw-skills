#!/usr/bin/env python3
"""小红书关键词搜索（可选增强源）—— 经 MediaCrawler 抓公开笔记，返回**结论性摘要**。

⚠️ 默认关闭。小红书无官方 API，本模块靠 MediaCrawler（Playwright + 你本人扫码登录）抓公开笔记，
属社区情报增强源——**个人、低频、善待平台**；遇验证码/封控直接放弃，不硬刚。详见
references/xiaohongshu.md（含 xhshow==0.1.9 版本坑）。

配置 ~/.birdwatch/config.json 的 xiaohongshu：
  enabled            是否启用（默认 false）
  mediacrawler_path  MediaCrawler 仓库目录（内含 .venv）
  max_notes          抓取上限（默认 10）

用法：
  python xhs_search.py --keywords "滨江森林公园 观鸟" [--location 滨江,滨森] [--top 8]
  python xhs_search.py --location 滨江 --no-crawl   # 只解析上次抓取结果，不再请求平台
输出：JSON {enabled, notes:[{title,date,likes,snippet,images,url}], note}
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import datetime

import birdwatch_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def venv_python(mc_path):
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        p = os.path.join(mc_path, rel)
        if os.path.exists(p):
            return p
    return sys.executable  # 退而求其次（可能缺依赖）


def parse_likes(v):
    """'324' / '1.2万' / '1万' / '10w+' -> int。"""
    s = str(v or "0").strip().lower().replace("+", "")
    m = re.match(r"([\d.]+)\s*(万|w)?", s)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * 10000) if m.group(2) else int(n)


def latest_jsonl(mc_path):
    pats = [os.path.join(mc_path, "data", "xhs", "jsonl", "*.jsonl"),
            os.path.join(mc_path, "data", "xhs", "json", "*.json")]
    files = []
    for p in pats:
        files += glob.glob(p)
    return max(files, key=os.path.getmtime) if files else None


def summarize_jsonl(path, location=None, top=8):
    """解析 MediaCrawler 笔记 jsonl → 摘要列表（按点赞降序，可按地点关键词过滤）。"""
    locs = [x for x in (location or "").split(",") if x.strip()]
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            title = r.get("title") or ""
            desc = (r.get("desc") or "").replace("\n", " ")
            blob = title + " " + desc
            if locs and not any(k in blob for k in locs):
                continue
            ts = r.get("time")
            date = (datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
                    if ts else "")
            imgs = [u for u in (r.get("image_list") or "").split(",") if u][:3]
            nid = r.get("note_id", "")
            rows.append({
                "title": title,
                "date": date,
                "likes": parse_likes(r.get("liked_count")),
                "snippet": re.sub(r"#[^#]+\[话题\]#", "", desc).strip()[:140],
                "images": imgs,
                "url": f"https://www.xiaohongshu.com/explore/{nid}" if nid else "",
            })
    rows.sort(key=lambda x: x["likes"], reverse=True)
    return rows[:top]


def run_crawl(mc_path, keyword, max_notes):
    """跑 MediaCrawler 抓取。返回最新 jsonl 路径（失败 None）。需仓库 .venv 与已登录态。"""
    py = venv_python(mc_path)
    cmd = [py, "main.py", "--platform", "xhs", "--lt", "qrcode", "--type", "search",
           "--keywords", keyword]
    try:
        subprocess.run(cmd, cwd=mc_path, capture_output=True, text=True,
                       encoding="utf-8", timeout=300)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"MediaCrawler 运行失败：{e}\n")
        return None
    return latest_jsonl(mc_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keywords", default="", help="搜索关键词（如 '滨江森林公园 观鸟'）")
    ap.add_argument("--location", default="", help="按地点关键词过滤结果，逗号分隔（如 滨江,滨森）")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--no-crawl", action="store_true", help="不请求平台，只解析上次抓取的 jsonl")
    args = ap.parse_args()

    enabled = cfg.flag("xiaohongshu.enabled", default=False)
    mc_path = cfg.get("xiaohongshu.mediacrawler_path", default="")
    max_notes = int(cfg.get("xiaohongshu.max_notes", default=10) or 10)

    if not enabled:
        print(json.dumps({"enabled": False, "notes": [],
                          "note": "小红书增强源未启用（xiaohongshu.enabled=false）——攻略将跳过该板块"},
                         ensure_ascii=False))
        return
    if not mc_path or not os.path.isdir(mc_path):
        print(json.dumps({"enabled": True, "notes": [],
                          "note": "未配置 xiaohongshu.mediacrawler_path 或路径无效"}, ensure_ascii=False))
        return

    path = latest_jsonl(mc_path) if args.no_crawl else None
    if not args.no_crawl:
        if not args.keywords:
            print(json.dumps({"enabled": True, "notes": [], "note": "缺 --keywords"}, ensure_ascii=False))
            return
        path = run_crawl(mc_path, args.keywords, max_notes)
    if not path:
        print(json.dumps({"enabled": True, "notes": [],
                          "note": "未获取到笔记（抓取失败/未登录/被限流）——跳过该板块"}, ensure_ascii=False))
        return

    notes = summarize_jsonl(path, location=args.location, top=args.top)
    print(json.dumps({"enabled": True, "source_file": os.path.basename(path),
                      "count": len(notes), "notes": notes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
