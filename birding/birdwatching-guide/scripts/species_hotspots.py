#!/usr/bin/env python3
"""菜鸟聚集地发现 —— 以"我还没加新的鸟种"为主语，反向找它在某地区/某月**报告最集中、且特异**的点位。

观鸟"打鸟"的逻辑：拍某只常见鸟，最好的办法是去它高频聚集的点。本脚本：
1. 取地区目标月（最近 N 年同月）公开鸟种（中国观鸟记录中心，带 taxon_id + 报告数），减去人生鸟单 = 可加新；
2. 对报告数靠前的可加新种，抽样其公开报告，按 point_name 聚合 → 集中度=最高点位报告占比；
3. 用大盘基线算 **lift**=该种在某点占比 ÷ 该点在全部报告占比，剔除"超级点哪都多"的观察者效应；
4. 按 "lift × 报告量 × 拍摄难度" 排序——既高频又**对该种特异**、且好拍的，才是真正值得专程去的"打鸟点"。

支持：--month（对齐目标月，跨年合并）、--regions（上海+周边）、lift（特异性）。
配置：~/.birdwatch/config.json（birdreport 走公开 /front 接口，无需 token；只需 Node）。

用法：python species_hotspots.py --month 6 [--years 2] [--regions 上海市/上海市,江苏省/苏州市,浙江省/嘉兴市]
                                [--scan 12] [--pages 2] [--top 14]
"""
import argparse
import calendar
import datetime
import json
import math
import os
import sys
import time
from collections import Counter

os.environ.setdefault("BIRDREPORT_MIN_INTERVAL", "5.0")  # 重扫易触发限流，间隔给足
import birdreport_public as B  # noqa: E402

# 结果缓存：聚合是"准静态"知识（某种某月聚集地变化慢），算过就存，避免重复打平台。
CACHE_PATH = os.path.expanduser("~/.birdwatch/species_points_cache.json")


def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(c):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

PHOTO_HARD = [
    (("杜鹃", "鹃"), 0.35),
    (("柳莺", "树莺", "苇莺", "蝗莺", "扇尾莺", "鳞头", "鹟莺"), 0.5),
    (("秧鸡", "田鸡", "苇鳽", "麻鳽", "董鸡"), 0.45),
    (("鸮", "鸺鹠", "夜鹰"), 0.4),
    (("雨燕",), 0.55),
]


def photo_factor(name):
    for kws, f in PHOTO_HARD:
        if any(k in name for k in kws):
            return f
    return 1.0


def load_lifelist():
    p = os.path.expanduser("~/.birdwatch/lifelist.json")
    try:
        with open(p, encoding="utf-8") as f:
            return {s.get("name") for s in json.load(f).get("species", []) if s.get("name")}
    except Exception:  # noqa: BLE001
        return set()


def month_windows(month, years):
    """目标月在最近 years 个完整年的窗口列表 [(start,end), ...]（最新在前）。"""
    today = datetime.date.today()
    base_year = today.year if month < today.month else today.year - 1
    out = []
    for y in range(base_year, base_year - years, -1):
        last = calendar.monthrange(y, month)[1]
        out.append((f"{y}-{month:02d}-01", f"{y}-{month:02d}-{last:02d}"))
    return out


def search_points(province, city, windows, taxonid="", pages=2):
    """跨窗口抽样公开报告，聚合 point_name。返回 (sampled, Counter)。taxonid 空=大盘基线。"""
    pts, sampled = Counter(), 0
    for start, end in windows:
        for page in range(1, pages + 1):
            body = {"page": page, "limit": 50, "taxonid": str(taxonid), "startTime": start,
                    "endTime": end, "province": province, "city": city, "district": "",
                    "pointname": "", "username": "", "serial_id": "", "ctime": "",
                    "taxonname": "", "state": "", "mode": "0", "outside_type": "0"}
            code, _, rows = B.front_call("/front/record/activity/search", body)
            if code != 0 or not isinstance(rows, list) or not rows:
                break  # 505/限流就停，不重试（重试只会加重平台负担、触发持续封禁）
            for r in rows:
                nm = r.get("point_name")
                if nm:
                    pts[f"{nm}"] += 1
                    sampled += 1
            if len(rows) < 50:
                break
    return sampled, pts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--month", type=int, required=True, help="目标月份 1-12（对齐出行季节）")
    ap.add_argument("--years", type=int, default=2, help="合并最近N年同月（默认2，越大越稳越慢）")
    ap.add_argument("--regions", default="上海市/上海市,江苏省/苏州市,浙江省/嘉兴市",
                    help="province/city 逗号分隔（上海+周边）")
    ap.add_argument("--scan", type=int, default=6,
                    help="本次最多扫描N个新种（保持低频善待平台；多次运行靠缓存累积覆盖）")
    ap.add_argument("--pages", type=int, default=1, help="每种每窗抽样页数(每页50)")
    ap.add_argument("--base-pages", type=int, default=2, help="大盘基线每窗抽样页数")
    ap.add_argument("--top", type=int, default=14, help="输出前N个(种,点)")
    ap.add_argument("--min-records", type=int, default=40, help="种的同月报告数下限")
    ap.add_argument("--min-point", type=int, default=4, help="首选点位最少报告数")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存，重新拉取（慎用，会打平台）")
    args = ap.parse_args()

    regions = [tuple(x.split("/")) for x in args.regions.split(",") if "/" in x]
    windows = month_windows(args.month, args.years)
    life = load_lifelist()
    cache = _load_cache()
    rkey = ",".join(f"{p}/{c}" for p, c in regions) + f"|m{args.month}|y{args.years}|p{args.pages}"
    sys.stderr.write(f"地区{regions} 月份{args.month} 窗口{[w[0][:7] for w in windows]}\n")

    def aggregate(taxonid, pages, ckey):
        """带缓存的跨区+跨年点位聚合。命中缓存直接返回，不打平台。"""
        if not args.refresh and ckey in cache:
            c = cache[ckey]
            return c["sampled"], Counter(c["points"])
        agg, sampled = Counter(), 0
        for prov, city in regions:
            s, pts = search_points(prov, city, windows, taxonid=taxonid, pages=pages)
            agg += pts
            sampled += s
        if sampled >= 8:  # 只缓存"拿到有效数据"的（被限流的不缓存，留待解封后补）
            cache[ckey] = {"sampled": sampled, "points": dict(agg)}
        return sampled, agg

    # 1) 物种选取：跨区+跨年合并报告数（taxon_id 全局一致）
    rec, tid, fam = Counter(), {}, {}
    for prov, city in regions:
        for start, end in windows:
            sp = B.region_taxa(prov, city, start=start, end=end, pages=4)
            for s in sp:
                n = s.get("name")
                if n:
                    rec[n] += s.get("recordcount") or 0
                    tid[n] = s.get("taxon_id")
                    fam[n] = s.get("family")
    new_sp = [(n, c) for n, c in rec.items() if n not in life and c >= args.min_records and tid.get(n)]
    new_sp.sort(key=lambda x: x[1], reverse=True)
    scan = new_sp[: args.scan]
    sys.stderr.write(f"可加新候选 {len(new_sp)}，扫描前 {len(scan)}\n")

    # 2) 大盘基线点位分布（无 taxon 过滤，跨区+跨年合并，缓存复用）
    base_total, base = aggregate("", args.base_pages, f"BASE|{rkey}|bp{args.base_pages}")
    sys.stderr.write(f"大盘基线 {base_total} 份报告，{len(base)} 个点\n")

    # 3) 逐种聚合点位 + lift（命中缓存的不打平台；本次只新拉未缓存的，保持低频）
    results = []
    for name, yr_rec in scan:
        sampled, agg = aggregate(tid[name], args.pages, f"{tid[name]}|{rkey}")
        _save_cache(cache)  # 每种存一次，中途被限流也保住已得
        if sampled < 8 or not agg:
            continue
        top_pt, top_c = agg.most_common(1)[0]
        conc = top_c / sampled
        if top_c < args.min_point:
            continue
        # lift：该种在该点的占比 ÷ 该点在大盘的占比（基线为0则给地板值，标稀有点）
        sp_share = top_c / sampled
        base_share = (base.get(top_pt, 0) / base_total) if base_total else 0
        if base_share > 0:
            lift = sp_share / base_share
            rare_pt = False
        else:
            lift = sp_share / (1.0 / max(base_total, 1))  # 地板：大盘没采到该点
            rare_pt = True
        pf = photo_factor(name)
        score = round(min(lift, 8) * min(1.0, top_c / 20) * pf, 3)  # lift 截顶防极端
        results.append({
            "species": name, "family": fam.get(name), "month_records": yr_rec,
            "sampled": sampled, "best_point": top_pt, "best_point_reports": top_c,
            "concentration": round(conc, 3), "lift": round(lift, 2), "rare_point": rare_pt,
            "hard_to_shoot": pf < 1,
            "top_points": [{"point": p, "reports": c} for p, c in agg.most_common(4)],
            "score": score,
        })
    results.sort(key=lambda x: x["score"], reverse=True)

    print(json.dumps({
        "source": "中国观鸟记录中心公开数据（可加新种→聚集地，含月份对齐+lift特异性）",
        "regions": [f"{p}/{c}" for p, c in regions],
        "month": args.month, "windows": [f"{w[0]}~{w[1]}" for w in windows],
        "baseline_reports": base_total,
        "note": "concentration=该种报告最集中点位占比；lift=该点对该种的特异度(>1.5 才算明显偏好，"
                "已剔除超级点观察者效应)；score=min(lift)×报告量×拍摄难度。rare_point=大盘基线未采到该点。",
        "scanned": len(scan),
        "targets": results[: args.top],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
