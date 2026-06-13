#!/usr/bin/env python3
"""目标智能推荐 —— 从"大本营"出发，综合 [可加新种 × 鸟种丰富度 × 通勤(高德) × 天气]
平衡打分，推荐最值得去的观鸟点 Top N。

数据：eBird 热点 + 逐点近期鸟种（算可加新，vs ~/.birdwatch/lifelist.json）；
     高德 Web服务（地理编码大本营、驾车距离/时长）；无高德 key 时退化为直线距离。
配置：~/.birdwatch/config.json 的 home_base（address 或 lng/lat + max_radius_km）、amap.key、ebird_api_key。

用法：python target_select.py [--radius 60] [--top 5] [--back 14]
输出：Top N 候选点（名称/距离/驾车时长/估算成本/可加新种数与示例/累计种数/打分）。
"""
import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

import birdwatch_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

EBIRD = "https://api.ebird.org/v2"
AMAP = "https://restapi.amap.com/v3"


def _get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ebird(path, params, key):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    return _get(f"{EBIRD}{path}?{qs}", headers={"x-ebirdapitoken": key})


def amap_geocode(address, key):
    d = _get(f"{AMAP}/geocode/geo?address={urllib.parse.quote(address)}&key={key}")
    if d.get("status") == "1" and d.get("geocodes"):
        lng, lat = d["geocodes"][0]["location"].split(",")
        return float(lng), float(lat)
    return None


def amap_commute(o_lng, o_lat, d_lng, d_lat, key, city):
    """高德通勤估算（用户出行=打车/公交，不自驾）：
    打车 = driving extensions=all 的 taxi_cost + 驾车时长；
    公交 = transit/integrated 的票价 cost + 时长。
    返回 {taxi_min, taxi_cost, transit_min, transit_cost}，取不到的为 None。"""
    out = {"taxi_min": None, "taxi_cost": None, "transit_min": None, "transit_cost": None}
    try:  # 打车
        r = _get(f"{AMAP}/direction/driving?origin={o_lng},{o_lat}&destination={d_lng},{d_lat}&extensions=all&key={key}")
        route = r.get("route", {})
        if route.get("paths"):
            out["taxi_min"] = round(int(route["paths"][0]["duration"]) / 60)
            if route.get("taxi_cost"):
                out["taxi_cost"] = round(float(route["taxi_cost"]))
    except Exception:  # noqa: BLE001
        pass
    try:  # 公交
        r = _get(f"{AMAP}/direction/transit/integrated?origin={o_lng},{o_lat}&destination={d_lng},{d_lat}&city={city}&key={key}")
        ts = r.get("route", {}).get("transits") or []
        if ts:
            out["transit_min"] = round(int(ts[0]["duration"]) / 60)
            if ts[0].get("cost"):
                out["transit_cost"] = round(float(ts[0]["cost"]), 1)
    except Exception:  # noqa: BLE001
        pass
    return out


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_lifelist():
    p = os.path.join(os.path.expanduser("~"), ".birdwatch", "lifelist.json")
    try:
        with open(p, encoding="utf-8") as f:
            return {s.get("name") for s in json.load(f).get("species", []) if s.get("name")}
    except Exception:  # noqa: BLE001
        return set()


def norm(vals):
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return [0.5 for _ in vals]
    return [(v - lo) / (hi - lo) for v in vals]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--radius", type=int, default=0, help="搜索半径km（默认取config home_base.max_radius_km）")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--back", type=int, default=14, help="逐点鸟种回溯天数")
    ap.add_argument("--enrich", type=int, default=12, help="对累计种数最高的前N个点做距离+鸟种富集")
    args = ap.parse_args()

    ekey = cfg.get("ebird_api_key", env="EBIRD_API_KEY")
    if not ekey:
        sys.exit("缺少 ebird_api_key")
    akey = cfg.get("amap.key", env="AMAP_KEY")
    city = cfg.get("home_base.citycode", default="021")  # 高德城市码（公交查询用），默认上海021
    radius = args.radius or int(cfg.get("home_base.max_radius_km", default=60))

    # 大本营经纬度
    lng = cfg.get("home_base.lng")
    lat = cfg.get("home_base.lat")
    if not (lng and lat):
        addr = cfg.get("home_base.address")
        if not addr:
            sys.exit("config 缺 home_base（address 或 lng/lat）")
        if not akey:
            sys.exit("home_base 只有地址、且无高德 key —— 无法地理编码。请在 config 填 amap.key 或直接填 home_base.lng/lat")
        geo = amap_geocode(addr, akey)
        if not geo:
            sys.exit(f"高德地理编码失败：{addr}")
        lng, lat = geo
        # 缓存回 config，后续运行免重复地理编码
        cfg.set_value("home_base.lng", lng)
        cfg.set_value("home_base.lat", lat)
        sys.stderr.write(f"大本营定位：{addr} -> {lng},{lat}（已缓存）\n")
    lng, lat = float(lng), float(lat)

    # 候选热点
    hotspots = ebird("/ref/hotspot/geo", {"lat": lat, "lng": lng, "dist": min(radius, 50),
                                          "fmt": "json"}, ekey)
    if not isinstance(hotspots, list) or not hotspots:
        sys.exit("附近无 eBird 热点")
    for h in hotspots:
        h["_rich"] = h.get("numSpeciesAllTime") or 0
    hotspots.sort(key=lambda x: x["_rich"], reverse=True)
    cands = hotspots[: args.enrich]

    life = load_lifelist()
    enriched = []
    for h in cands:
        loc_id = h.get("locId")
        h_lat, h_lng = h.get("lat"), h.get("lng")
        # 距离/时长
        dist_km = round(haversine_km(lat, lng, h_lat, h_lng), 1)
        cm = {"taxi_min": None, "taxi_cost": None, "transit_min": None, "transit_cost": None}
        if akey:
            cm = amap_commute(lng, lat, h_lng, h_lat, akey, city)
        # 逐点近期鸟种 -> 可加新
        new_species = []
        try:
            obs = ebird(f"/data/obs/{loc_id}/recent", {"back": args.back, "sppLocale": "zh_SIM"}, ekey)
            seen = {o.get("comName") for o in obs}
            new_species = sorted(n for n in seen if n and n not in life)
        except Exception:  # noqa: BLE001
            pass
        enriched.append({
            "name": h.get("locName"), "locId": loc_id, "dist_km": dist_km,
            "taxi_min": cm["taxi_min"], "taxi_cost": cm["taxi_cost"],
            "transit_min": cm["transit_min"], "transit_cost": cm["transit_cost"],
            "richness": h["_rich"], "new_count": len(new_species),
            "new_sample": new_species[:8],
        })

    # 平衡打分：可加新 0.4 + 丰富度 0.25 + 近(时长或距离) 0.35
    lifers = norm([e["new_count"] for e in enriched])
    rich = norm([e["richness"] for e in enriched])
    # 通勤：公交时长(可达性) + 打车费(便利成本)；取不到时用直线距离做兜底代理
    # 公交取不到=很可能不可达，按"很差"惩罚（而非用直线距离兜底，否则反而帮它）
    t_metric = [e["transit_min"] if e["transit_min"] is not None else 600 for e in enriched]
    c_metric = [e["taxi_cost"] if e["taxi_cost"] is not None else 500 for e in enriched]
    near_t = norm([-v for v in t_metric])  # 公交越快越高
    near_c = norm([-v for v in c_metric])  # 打车越便宜越高
    for i, e in enumerate(enriched):
        commute = (near_t[i] + near_c[i]) / 2  # 通勤便利 = 公交省时 + 打车省钱
        e["score"] = round(0.4 * lifers[i] + 0.25 * rich[i] + 0.35 * commute, 3)
    enriched.sort(key=lambda x: x["score"], reverse=True)

    print(json.dumps({
        "home_base": cfg.get("home_base.address"),
        "radius_km": radius,
        "transport": "打车+公交（不自驾）" if akey else "未接高德(仅直线距离)",
        "weight": "平衡(可加新0.4/丰富度0.25/通勤0.35[公交时长+打车费])",
        "candidates": enriched[: args.top],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
