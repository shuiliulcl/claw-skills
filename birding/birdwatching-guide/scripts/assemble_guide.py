#!/usr/bin/env python3
"""一条命令生成「带路网地图」的离线 HTML 观鸟攻略（Phase 2 组装器）。

编排本目录下的采集脚本 + eBird 中文数据，按攻略口径组装成自包含 HTML：
  - 🎯 高成功率·可加新：点位级报告数(中国观鸟记录中心) × 拍摄难度降权，剔除偶现种
  - ✨ 可遇不可求：eBird 罕见/高光（降级为彩蛋，标"易空军"）
  - 🗺️ 园内路线图：hotspot_detail 的真实道路折线静态地图（base64 内嵌，key 不入 HTML）
  - ⏰ 高频出鸟时段：eBird checklist 提交时刻直方图
  - ☀️ 天气、🚇 通勤（高德打车/公交）、📈 鸟况时间线

依赖同目录：qweather_fetch.py / hotspot_detail.py / birdreport_public.py / target_select.py(通勤) / birdwatch_config.py。
用法：python assemble_guide.py --name 世纪公园 --lng 121.5496 --lat 31.2149 --locId L1029418 \
        [--province 上海市 --city 上海市] [--out 观鸟攻略_世纪公园.html]
"""
import argparse
import base64
import datetime
import html
import io
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

import birdwatch_config as cfg
import xhs_search

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# 闻声难见/隐蔽/夜行等难拍种 → 拍到概率折扣（与 species_hotspots.py 同口径）
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


def run_json(script, args, timeout=120):
    """跑同目录脚本，stdout 解析为 JSON。失败返回 None。"""
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, script), *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        if p.stdout and p.stdout.strip().startswith(("{", "[")):
            return json.loads(p.stdout)
        sys.stderr.write(f"[{script}] 无有效输出: {(p.stderr or '')[:200]}\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[{script}] 失败: {e}\n")
    return None


def ebird(path, params, key):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    req = urllib.request.Request(f"https://api.ebird.org/v2{path}?{qs}",
                                 headers={"x-ebirdapitoken": key})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))


def esc(s):
    return html.escape(str(s if s is not None else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--lng", required=True)
    ap.add_argument("--lat", required=True)
    ap.add_argument("--locId", default="")
    ap.add_argument("--province", default="上海市")
    ap.add_argument("--city", default="上海市")
    ap.add_argument("--out", default="")
    ap.add_argument("--taxa-days", type=int, default=90, help="点位级鸟种统计回溯天数(当季常见度，默认90)")
    ap.add_argument("--xhs-location", default="", help="小红书情报按此地点关键词过滤(逗号分隔)，默认用--name")
    args = ap.parse_args()

    ekey = cfg.get("ebird_api_key", env="EBIRD_API_KEY")
    if not ekey:
        sys.exit("缺 ebird_api_key")
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=args.taxa_days)).isoformat()
    end = today.isoformat()
    workdir = os.path.join(HERE, "..", ".cache")
    os.makedirs(workdir, exist_ok=True)
    mappng = os.path.abspath(os.path.join(workdir, "route_map.png"))

    # ---- 采集 ----
    weather = run_json("qweather_fetch.py", ["--lng", args.lng, "--lat", args.lat]) or []
    route = run_json("hotspot_detail.py", ["--name", args.name, "--lng", args.lng,
                     "--lat", args.lat] + (["--locId", args.locId] if args.locId else [])
                     + ["--map-out", mappng]) or {}
    pt = run_json("birdreport_public.py", ["--taxa", "--pointname", args.name,
                  "--province", args.province, "--city", args.city,
                  "--start", start, "--end", end], timeout=200) or {"species": []}

    life = set()
    try:
        with io.open(os.path.expanduser("~/.birdwatch/lifelist.json"), encoding="utf-8") as f:
            life = {s["name"] for s in json.load(f).get("species", []) if s.get("name")}
    except Exception:  # noqa: BLE001
        pass

    notable, recent = [], []
    try:
        notable = ebird("/data/obs/geo/recent/notable",
                        {"lat": args.lat, "lng": args.lng, "dist": 20, "back": 14,
                         "detail": "full", "sppLocale": "zh_SIM"}, ekey)
    except Exception:  # noqa: BLE001
        pass
    if args.locId:
        try:
            recent = ebird(f"/data/obs/{args.locId}/recent", {"back": 10, "sppLocale": "zh_SIM"}, ekey)
        except Exception:  # noqa: BLE001
            pass

    # 通勤（高德打车/公交；缺 home_base/key 则跳过）
    commute = None
    try:
        import target_select as TS
        akey = cfg.get("amap.key", env="AMAP_KEY")
        hlng, hlat = cfg.get("home_base.lng"), cfg.get("home_base.lat")
        if akey and hlng and hlat:
            commute = TS.amap_commute(float(hlng), float(hlat), float(args.lng), float(args.lat),
                                      akey, cfg.get("home_base.citycode", default="021"))
    except Exception:  # noqa: BLE001
        pass

    # 小红书情报（可选，启用时读最近一次抓取结果，不在组装时联网）
    xhs_notes = []
    if cfg.flag("xiaohongshu.enabled", default=False):
        mc = cfg.get("xiaohongshu.mediacrawler_path", default="")
        latest = xhs_search.latest_jsonl(mc) if mc and os.path.isdir(mc) else None
        if latest:
            try:
                xhs_notes = xhs_search.summarize_jsonl(latest, location=(args.xhs_location or args.name), top=6)
            except Exception:  # noqa: BLE001
                pass

    def isnew(n):
        return n not in life

    # ===== 稳拍可加新榜：点位 recordcount × 拍摄难度，剔除 recordcount<2 =====
    MIN_RC = 2
    sp = pt.get("species", [])
    stable = [s for s in sp if s.get("name") and isnew(s["name"]) and (s.get("recordcount") or 0) >= MIN_RC]
    for s in stable:
        s["_f"] = photo_factor(s["name"])
        s["_adj"] = (s.get("recordcount") or 0) * s["_f"]
    stable.sort(key=lambda s: s["_adj"], reverse=True)
    max_adj = max((s["_adj"] for s in stable), default=1) or 1
    owned = sorted([s for s in sp if s.get("name") and not isnew(s["name"]) and (s.get("recordcount") or 0) >= MIN_RC],
                   key=lambda s: s.get("recordcount") or 0, reverse=True)

    def stars(s):
        return "★" * max(1, min(5, round(s["_adj"] / max_adj * 5)))

    # ===== 高光（彩蛋） =====
    seen, rares = set(), []
    for o in notable:
        n = o.get("comName")
        if n and n not in seen:
            seen.add(n)
            rares.append({"name": n, "dt": (o.get("obsDt") or "")[:10], "new": isnew(n)})
    rares = rares[:6]

    # ===== 时间线 =====
    tl = {}
    for o in recent:
        d = (o.get("obsDt") or "")[:10]
        tl.setdefault(d, []).append(o.get("comName"))
    timeline = sorted(tl.items(), reverse=True)[:5]

    # ===== 地图 base64 =====
    map_b64 = ""
    if os.path.exists(mappng):
        map_b64 = base64.b64encode(io.open(mappng, "rb").read()).decode("ascii")

    # ---- 渲染片段 ----
    wcards = ""
    for d in weather:
        try:
            best = " best" if d.get("textDay") in ("晴", "多云") and float(d.get("precip", "9")) < 1 else ""
        except Exception:  # noqa: BLE001
            best = ""
        wcards += (f'<div class="wday{best}"><div class="d">{esc(d.get("date","")[5:])} {esc(d.get("textDay"))}</div>'
                   f'<div class="t">{esc(d.get("tempMin"))}~{esc(d.get("tempMax"))}°C</div>'
                   f'<div class="mini">{esc(d.get("windDirDay"))} {esc(d.get("windScaleDay"))}级 · 降水{esc(d.get("precip"))}mm</div>'
                   f'<div class="mini">日出{esc(d.get("sunrise"))} / 日落{esc(d.get("sunset"))}</div>'
                   f'<div class="hint">{esc(d.get("birdingHint"))}</div></div>')

    stable_rows = ""
    for s in stable[:14]:
        hard = ' <span class="hard">难拍</span>' if s["_f"] < 1 else ""
        stable_rows += (f'<tr><td><b>{esc(s["name"])}</b> <span class="fam">{esc(s.get("family") or "")}</span>{hard}</td>'
                        f'<td class="rc">{esc(s["recordcount"])}次</td><td class="st">{stars(s)}</td></tr>')
    owned_str = "、".join(esc(s["name"]) for s in owned[:12])

    rare_cards = "".join(
        f'<span class="rare {"rn" if r["new"] else ""}">{esc(r["name"])}{" ⭐可加新" if r["new"] else ""} <i>{esc(r["dt"])}</i></span>'
        for r in rares) or '<span class="sub">近14天该区域无明显罕见记录</span>'

    routerows = (f'<div class="hotspot"><span class="rank">起</span><strong>{esc(route.get("entrance",""))}</strong> '
                 f'<span class="sp">入口</span></div>')
    for i, s in enumerate(route.get("route", [])):
        routerows += (f'<div class="hotspot"><span class="rank">{i+1}</span><strong>{esc(s.get("name"))}</strong> '
                      f'<span class="sp">步行 {esc(s.get("walk_from_prev","—"))}</span></div>')
    route_birds = "、".join(esc(b) for b in route.get("key_birds", [])[:14])
    map_img = (f'<img class="map" src="data:image/png;base64,{map_b64}" alt="园内路线图">'
               if map_b64 else '<p class="sub">地图暂缺</p>')

    # 活跃时段
    act = route.get("active_hours") or {}
    act_html = ""
    bh = act.get("by_hour") or {}
    if bh:
        mx = max(bh.values()) or 1
        bars = ""
        for h, n in bh.items():
            ph = max(4, round(n / mx * 100))
            hot = " hot" if str(act.get("peak", "")).startswith(h) or str(act.get("secondary", "") or "").startswith(h) else ""
            bars += f'<div class="barcol"><div class="bar{hot}" style="height:{ph}%"></div><div class="hl">{esc(h)}</div></div>'
        peak = f'<b>{esc(act.get("peak",""))}</b>（{round(act.get("peak_share",0)*100)}%出勤）'
        sec = f' · 次高峰 <b>{esc(act["secondary"])}</b>（{round(act.get("secondary_share",0)*100)}%）' if act.get("secondary") else ""
        act_html = (f'<section><h2>⏰ 高频出鸟时段（该点位）</h2>'
                    f'<div class="sub">基于 eBird 近 {esc(act.get("samples"))} 份清单的提交时刻——大家几点最常来出鸟。早高峰 {peak}{sec}</div>'
                    f'<div class="bars">{bars}</div>'
                    f'<div class="tip">🌅 主攻 <b>{esc(act.get("peak",""))}</b>；睡过头可补 <b>{esc(act.get("secondary","—"))}</b> 午后场。正午鸟少光硬，适合休息。</div></section>')

    tlrows = "".join(f'<li><span class="when">{esc(d)}</span>'
                     f'<div class="mini">{esc("、".join(dict.fromkeys(spp))[:90])}</div></li>'
                     for d, spp in timeline) or '<li class="sub">暂无</li>'

    if commute and (commute.get("transit_min") or commute.get("taxi_min")):
        tcell = f'约 {commute["transit_min"]} 分钟 · ¥{commute.get("transit_cost","?")}' if commute.get("transit_min") else "公交方案不可达"
        xcell = f'约 {commute["taxi_min"]} 分钟 · ¥{commute.get("taxi_cost","?")}' if commute.get("taxi_min") else "—"
        commute_html = (f'<section><h2>🚇 怎么去（不自驾）</h2><div class="commute">'
                        f'<div class="cbox"><b>公交</b><br>{esc(tcell)}</div>'
                        f'<div class="cbox"><b>打车</b><br>{esc(xcell)}</div></div></section>')
    else:
        commute_html = ""

    # 🔴 小红书情报板块
    xhs_html = ""
    if xhs_notes:
        cards = ""
        for n in xhs_notes:
            link = f' <a href="{esc(n["url"])}" target="_blank">原帖↗</a>' if n.get("url") else ""
            cards += (f'<div class="xhs"><div class="xt">{esc(n["title"])}</div>'
                      f'<div class="xm">❤{esc(n["likes"])} · {esc(n["date"])}{link}</div>'
                      f'<div class="xs">{esc(n["snippet"])}</div></div>')
        xhs_html = (f'<section><h2>🔴 鸟友情报（小红书）</h2>'
                    f'<div class="sub">近期公开笔记摘要（按热度），含微点位/机位/季节提醒——社区情报，时效性强、需自行甄别</div>'
                    f'<div class="xhsgrid">{cards}</div></section>')

    out_path = args.out or f"观鸟攻略_{args.name}_{today.isoformat()}.html"
    HTML = TEMPLATE.format(
        name=esc(args.name), date=today.isoformat(), commute=commute_html, wcards=wcards,
        stable_rows=stable_rows or '<tr><td class="sub">点位级数据暂缺</td></tr>',
        owned=owned_str or "—", rares=rare_cards, total_walk=esc(route.get("total_walk", "")),
        entrance=esc(route.get("entrance", "")), n_stops=len(route.get("route", [])),
        map_img=map_img, routerows=routerows, route_birds=route_birds or "—",
        act_html=act_html, tlrows=tlrows, xhs_html=xhs_html)
    io.open(out_path, "w", encoding="utf-8").write(HTML)

    # 自检
    bad = sum(HTML.count(x) for x in ("{{", "restapi.amap", "x-ebirdapitoken"))
    print(json.dumps({
        "out": os.path.abspath(out_path), "kb": round(len(HTML) / 1024),
        "stable_new": len(stable), "owned_common": len(owned), "rares": len(rares),
        "map": bool(map_b64), "active_hours": bool(bh), "commute": bool(commute_html),
        "selfcheck_leak_or_placeholder": bad,
    }, ensure_ascii=False))


TEMPLATE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"><title>观鸟攻略 · {name}</title>
<style>
:root{{--green:#4a7c59;--green-d:#2f5233;--cream:#f5f1e6;--accent:#e08a3c;}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--cream);color:#2b2b2b;line-height:1.6;padding-bottom:40px}}
header{{background:var(--green-d);color:#fff;padding:28px 20px;text-align:center}}header h1{{font-size:24px}}header .meta{{margin-top:8px;opacity:.85;font-size:12.5px}}
.wrap{{max-width:880px;margin:0 auto;padding:0 16px}}section{{background:#fff;border-radius:14px;padding:18px 20px;margin-top:18px;box-shadow:0 2px 10px rgba(0,0,0,.05)}}
h2{{color:var(--green-d);font-size:18px;margin-bottom:6px}}.sub{{color:#7a7a6e;font-size:12.5px;margin-bottom:12px}}.mini{{font-size:12px;color:#666}}
.weather{{display:flex;gap:9px;flex-wrap:wrap}}.wday{{flex:1;min-width:140px;border:1px solid #ececdf;border-radius:10px;padding:11px;background:#fcfbf6}}.wday.best{{border-color:var(--accent);box-shadow:0 0 0 2px rgba(224,138,60,.15)}}
.wday .d{{font-weight:600;color:var(--green-d)}}.wday .t{{font-size:17px;margin:3px 0}}.wday .hint{{font-size:12px;color:var(--accent);margin-top:5px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td{{padding:7px 8px;border-bottom:1px solid #f0efe6;vertical-align:middle}}
.fam{{color:#9a9a8c;font-size:11px}}.rc{{color:var(--green-d);white-space:nowrap;text-align:right}}.st{{color:var(--accent);white-space:nowrap}}
.hard{{background:#eee;color:#999;font-size:10.5px;padding:1px 6px;border-radius:8px}}
.commute{{display:flex;gap:10px;flex-wrap:wrap}}.cbox{{flex:1;min-width:140px;border:1px solid #ececdf;border-radius:10px;padding:11px;background:#fcfbf6}}.cbox b{{color:var(--green-d)}}
.tip{{background:#e7f3e9;border-radius:8px;padding:9px 12px;margin-top:10px;font-size:13.5px}}
.rare{{display:inline-block;background:#f1f0e7;color:#777;border-radius:8px;padding:4px 10px;margin:3px 4px 0 0;font-size:13px}}.rare.rn{{background:#fbe9d6;color:#a85e1e}}.rare i{{color:#aaa;font-style:normal;font-size:11px}}
.map{{width:100%;border-radius:10px;border:1px solid #e3e3d5;display:block}}
.hotspot{{padding:7px 0;border-bottom:1px dashed #e3e3d5}}.hotspot:last-child{{border:none}}.rank{{display:inline-block;background:var(--green);color:#fff;border-radius:50%;width:23px;height:23px;text-align:center;line-height:23px;font-size:12px;margin-right:8px}}.sp{{color:var(--accent);font-size:12px}}
.bars{{display:flex;align-items:flex-end;gap:4px;height:120px;padding-top:6px}}.barcol{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}}
.bar{{width:70%;background:#cfe0d3;border-radius:3px 3px 0 0}}.bar.hot{{background:var(--accent)}}.hl{{font-size:9.5px;color:#999;margin-top:3px}}
.timeline{{list-style:none;border-left:2px solid var(--green);margin-left:6px}}.timeline li{{position:relative;padding:0 0 13px 18px}}.timeline li::before{{content:"";position:absolute;left:-7px;top:6px;width:11px;height:11px;border-radius:50%;background:var(--green)}}.timeline .when{{font-weight:600;color:var(--green-d);font-size:13px}}
.xhsgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}}.xhs{{border:1px solid #f0d6d6;border-radius:10px;padding:11px;background:#fff8f8}}.xhs .xt{{font-weight:600;color:#c0392b;font-size:14px}}.xhs .xm{{font-size:11px;color:#999;margin:4px 0}}.xhs .xm a{{color:#c0392b;text-decoration:none}}.xhs .xs{{font-size:12.5px;color:#555}}
footer{{text-align:center;color:#999;font-size:12px;margin-top:24px}}
</style></head><body>
<header><h1>🦅 {name} · 观鸟攻略</h1>
<div class="meta">生成于 {date} ｜ 数据：eBird · 和风 · 中国观鸟记录中心 · 高德</div></header>
<div class="wrap">
{commute}
<section><h2>🎯 高成功率·可加新（优先冲这些）</h2>
<div class="sub">按该点「报告次数 × 拍摄难度」排序——越靠前=越常见越好拍越不易空军。闻声难见种（杜鹃/小型莺/秧鸡等）已降权标「难拍」；已剔除偶现种。</div>
<table>{stable_rows}</table>
<div class="tip">📷 这些是<b>本点最值得拿下的新种</b>。<br>✅ 已记录的常见种（可练拍）：{owned}</div></section>
<section><h2>✨ 可遇不可求（彩蛋，别强求）</h2>
<div class="sub">eBird 近14天罕见/高光——出现概率低，容易空军，<b>当惊喜而非目标</b></div>
<div>{rares}</div></section>
<section><h2>🗺️ 园内路线图（约 {total_walk}）</h2>
<div class="sub">从 <b>{entrance}</b> 进 · 🟠起=入口 🟢1..{n_stops}=途经点位 · 蓝线=沿真实园路的步行路线 · 数据：高德</div>
{map_img}
<div style="margin-top:12px">{routerows}</div>
<div class="tip">沿途重点鸟种：{route_birds}</div></section>
<section><h2>☀️ 天气与最佳时段</h2><div class="sub">和风天气未来3天 · 清晨日出后/傍晚日落前为黄金时段</div>
<div class="weather">{wcards}</div></section>
{act_html}
{xhs_html}
<section><h2>📈 近期鸟况时间线</h2><div class="sub">eBird 园内近期观测</div>
<ul class="timeline">{tlrows}</ul></section>
<footer>本攻略由 birdwatching-guide skill 生成 · eBird / 和风天气 / 中国观鸟记录中心 / 高德 · 仅供参考</footer>
</div></body></html>"""


if __name__ == "__main__":
    main()
