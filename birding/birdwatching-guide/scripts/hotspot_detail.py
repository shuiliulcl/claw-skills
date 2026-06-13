#!/usr/bin/env python3
"""点内地图微攻略 —— 给定一个观鸟大点位，产出"从几号门进 → 园内绕哪些地物/观鸟位 →
看什么鸟 → 步行路线时长"，供攻略做地图路线。

数据：高德 POI（place/around 找门/湖/林/湿地等）+ 高德步行路径规划（连成路线）
     + eBird（该点高光/近期鸟种，作"看什么鸟"）。
配置：~/.birdwatch/config.json 的 amap.key、ebird_api_key。

用法：python hotspot_detail.py --name 世纪公园 --lng 121.5496 --lat 31.2149 [--locId L1029418] [--radius 1500]
     加 --map-out route.png 会顺带下载一张高德静态地图（门+各点位编号+步行连线），
     供攻略内嵌（key 留在本地，不写进 HTML）。
"""
import argparse
import json
import math
import re
import sys
import urllib.parse
import urllib.request

import birdwatch_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

EBIRD = "https://api.ebird.org/v2"
AMAP = "https://restapi.amap.com/v3"
# 园内地物关键词（观鸟相关）
FEATURE_KW = "湖|湿地|森林|树林|芦苇|滩|池|观景台|码头|鸟岛|花园|草坪|河"


def _get(url, headers=None):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=headers or {}), timeout=25).read().decode("utf-8"))


def amap_poi(lng, lat, keywords, radius, key, limit=25):
    url = (f"{AMAP}/place/around?location={lng},{lat}&radius={radius}"
           f"&keywords={urllib.parse.quote(keywords)}&offset={limit}&page=1&key={key}")
    d = _get(url)
    out = []
    if d.get("status") == "1":
        for p in d.get("pois", []):
            loc = p.get("location", "")
            if "," in loc:
                plng, plat = map(float, loc.split(","))
                out.append({"name": p.get("name"), "type": (p.get("type") or "").split(";")[0],
                            "lng": plng, "lat": plat})
    return out


def amap_walk(o_lng, o_lat, d_lng, d_lat, key):
    """步行：返回 (距离米, 时长秒, 实际道路折线点[ "lng,lat", ... ])。"""
    try:
        d = _get(f"{AMAP}/direction/walking?origin={o_lng},{o_lat}&destination={d_lng},{d_lat}&key={key}")
        if d.get("status") == "1" and d.get("route", {}).get("paths"):
            p = d["route"]["paths"][0]
            pts = []
            for st in p.get("steps", []):
                pl = st.get("polyline") or ""
                if pl:
                    pts.extend(pl.split(";"))
            return int(p["distance"]), int(p["duration"]), pts
    except Exception:  # noqa: BLE001
        pass
    return None


def downsample(pts, cap=140):
    """折线点过多会撑爆静态地图 URL，等距降采样到 <=cap，保留首尾。"""
    if len(pts) <= cap:
        return pts
    step = (len(pts) + cap - 1) // cap
    out = pts[::step]
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def hav(lat1, lng1, lat2, lng2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def ebird(path, params, key):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    return _get(f"{EBIRD}{path}?{qs}", headers={"x-ebirdapitoken": key})


def build_staticmap_url(pts, key, size="720*480", path_pts=None):
    """pts=[{label,lng,lat}] 顺序即步行顺序，pts[0] 为入口；每点一个编号 marker。
    path_pts=["lng,lat",...] 为真实道路折线（来自步行规划）；缺省则点间直连。"""
    groups = []
    for i, p in enumerate(pts):
        color = "0xF56A00" if i == 0 else "0x2F5233"  # 入口橙、点位绿
        groups.append(f"mid,{color},{p['label']}:{p['lng']},{p['lat']}")
    markers = "|".join(groups)
    line = path_pts if path_pts else [f"{p['lng']},{p['lat']}" for p in pts]
    path = "6,0x1E88E5,1,,:" + ";".join(line)
    q = (f"size={size}"
         f"&markers={urllib.parse.quote(markers, safe=':,;|')}"
         f"&paths={urllib.parse.quote(path, safe=':,;|')}"
         f"&key={key}")
    return f"{AMAP}/staticmap?{q}"


def download(url, out_path):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
        data = r.read()
    with open(out_path, "wb") as f:
        f.write(data)
    return len(data)


def active_hours(loc_id, key, max_results=200):
    """该点位高频活动时段：拉近 N 条 checklist 的提交时刻(obsTime)做小时直方图，
    找最佳 3 小时窗（及分离的次高峰）。这是'大家几点来出鸟'的可靠代理。"""
    try:
        lists = ebird(f"/product/lists/{loc_id}", {"maxResults": max_results}, key)
    except Exception:  # noqa: BLE001
        return None
    hrs = {}
    for x in lists:
        t = x.get("obsTime")
        if t and ":" in t:
            h = int(t.split(":")[0])
            hrs[h] = hrs.get(h, 0) + 1
    total = sum(hrs.values())
    if total < 12:  # 样本太少不下结论
        return {"samples": total, "note": "样本不足，按通用黄金时段（日出后/日落前）即可"}

    def win_sum(c):  # 以 c 为起点的 3 小时窗计数
        return sum(hrs.get(h, 0) for h in (c, c + 1, c + 2))
    starts = range(5, 19)
    primary = max(starts, key=win_sum)
    psum = win_sum(primary)
    # 次高峰：与主峰错开 ≥3h，且达到主峰 55% 以上才算
    sec = max((c for c in starts if abs(c - primary) >= 3),
              key=win_sum, default=None)
    ssum = win_sum(sec) if sec is not None else 0
    out = {
        "samples": total,
        "peak": f"{primary:02d}:00-{primary + 3:02d}:00",
        "peak_share": round(psum / total, 2),
        "by_hour": {f"{h:02d}": hrs.get(h, 0) for h in range(5, 20)},
    }
    if sec is not None and ssum >= 0.55 * psum:
        out["secondary"] = f"{sec:02d}:00-{sec + 3:02d}:00"
        out["secondary_share"] = round(ssum / total, 2)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--lng", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--locId", default="")
    ap.add_argument("--radius", type=int, default=1500)
    ap.add_argument("--max-stops", type=int, default=6)
    ap.add_argument("--map-out", default="", help="下载高德静态地图PNG到此路径（含门+点位编号+步行连线）")
    args = ap.parse_args()

    akey = cfg.get("amap.key", env="AMAP_KEY")
    ekey = cfg.get("ebird_api_key", env="EBIRD_API_KEY")
    if not akey:
        sys.exit("缺少 amap.key（地图微攻略依赖高德）")

    # 按【园名】搜 POI（而非裸"门/湖"，否则抓来门窗店/大闸蟹餐厅），再按类型/名字筛
    pois = amap_poi(args.lng, args.lat, args.name, args.radius, akey, limit=50)
    # 门：名字含"X号门"
    gates, gseen = [], set()
    for p in pois:
        m = re.search(r"(\d+号门)", p["name"])
        if m and m.group(1) not in gseen:
            gseen.add(m.group(1)); gates.append({**p, "gate": m.group(1)})
    # 园内地物：类型为风景名胜、名字含园名、排除停车场/园名本身
    BIRD_KW = ("湖", "林", "湿地", "滩", "草坪", "苇", "岛", "河", "池", "荷", "园")
    feats, fseen = [], set()
    for p in pois:
        nm = p["name"]
        if (p["type"].startswith("风景名胜") and args.name in nm and "停车" not in nm
                and nm not in (args.name, "上海" + args.name) and nm not in fseen):
            fseen.add(nm); feats.append(p)
    # 观鸟相关地物优先（湖/林/湿地…），再按离中心近
    feats.sort(key=lambda f: (0 if any(k in f["name"] for k in BIRD_KW) else 1,
                              hav(args.lat, args.lng, f["lat"], f["lng"])))
    feats = feats[: args.max_stops]

    # 2) 路线：选离中心最近的门为起点，贪心最近邻串地物，高德步行算每段
    start = min(gates, key=lambda g: hav(args.lat, args.lng, g["lat"], g["lng"])) if gates else \
        {"name": "主入口(估)", "lng": args.lng, "lat": args.lat}
    route, total_m, total_s = [], 0, 0
    road_pts = [f"{start['lng']},{start['lat']}"]  # 真实道路折线（含入口起点）
    cur = start
    remaining = feats[:]
    while remaining:
        nxt = min(remaining, key=lambda f: hav(cur["lat"], cur["lng"], f["lat"], f["lng"]))
        remaining.remove(nxt)
        leg = amap_walk(cur["lng"], cur["lat"], nxt["lng"], nxt["lat"], akey)
        if leg:
            total_m += leg[0]; total_s += leg[1]
            road_pts.extend(leg[2])  # 拼接该段真实道路点
        nxt["walk_from_prev"] = f"{round(leg[0])}m/{round(leg[1] / 60)}分" if leg else "—"
        route.append(nxt)
        cur = nxt
    road_pts = downsample(road_pts)

    # 3) 看什么鸟（eBird 该点近期/高光）
    key_birds, act = [], None
    if ekey and args.locId:
        try:
            obs = ebird(f"/data/obs/{args.locId}/recent", {"back": 14, "sppLocale": "zh_SIM"}, ekey)
            key_birds = [o.get("comName") for o in obs if o.get("comName")][:20]
        except Exception:  # noqa: BLE001
            pass
        act = active_hours(args.locId, ekey)

    # 4) 静态地图（入口=起，点位按顺序编号 1..N；用 paths 连成步行线）
    map_pts = [{"label": "起", "lng": start["lng"], "lat": start["lat"]}]
    for i, s in enumerate(route):
        map_pts.append({"label": str(i + 1), "lng": s["lng"], "lat": s["lat"]})
    map_url = build_staticmap_url(map_pts, akey, path_pts=road_pts)
    map_out, map_bytes = "", 0
    if args.map_out and len(map_pts) >= 2:
        try:
            map_bytes = download(map_url, args.map_out)
            map_out = args.map_out
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"静态地图下载失败：{e}\n")

    print(json.dumps({
        "hotspot": args.name,
        "entrance": start.get("gate", start["name"]),
        "entrance_loc": {"lng": start["lng"], "lat": start["lat"]},
        "gates_found": [g.get("gate", g["name"]) for g in gates[:8]],
        "route": [{"name": s["name"], "type": s.get("type"), "lng": s["lng"], "lat": s["lat"],
                   "walk_from_prev": s.get("walk_from_prev", "—")} for s in route],
        "total_walk": f"{round(total_m)}m / {round(total_s/60)}分钟",
        "key_birds": key_birds,
        "active_hours": act,
        "map_points": map_pts,
        "map_out": map_out or None,
        "map_bytes": map_bytes or None,
        "note": "路线为基于地图地物的建议环线；鸟种为该点 eBird 近期记录，具体停留位以现场为准。"
                "地图编号「起」=入口，1..N=途经点位，蓝线为步行顺序。",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
