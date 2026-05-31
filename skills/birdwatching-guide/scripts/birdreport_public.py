#!/usr/bin/env python3
"""中国观鸟记录中心 —— 公开数据（/front/ 签名式接口，无需登录 token）。

与 birdreport_fetch.py（/member/ 个人记录，需 token）不同：本脚本走 /front/ 公开通道，
拿的是**所有鸟友**在某地区的公开记录，适合攻略的"区域鸟况"。

机制（qBird 老方案，仍有效）：请求体 RSA 加密 + 头 requestId/sign/timestamp
（sign=md5(明文+requestId+timestamp）），响应 AES（不同端点 key 不同，两 key 都试）。
加解密走 Node 助手 scripts/birdreport/front_helper.js（用站点原版 jQuertAjax）。

依赖：Node.js + scripts/birdreport/{jQuertAjax.js, node_modules/{crypto-js,jsdom}}、pycryptodome。

用法:
  python birdreport_public.py --province 上海市 --city 上海市 --start 2026-05-20 --end 2026-05-29
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER = os.path.join(HERE, "birdreport", "front_helper.js")
_KEYS = [(b"C8EB5514AF5ADDB94B2207B08C66601C", b"55DD79C6F04E1A67"),   # 新（记录类）
         (b"3583ec0257e2f4c8195eec7410ff1619", b"d93c0d5ec6352f20")]   # 老（图表类）

# === 速率控制：避免触发服务端 505 限流 ===
# 实测短时间多次调 /front/record/activity/search 会被限流，且持续数分钟。
# 此处对**进程内所有 front_call**做最小间隔保护（统一 2.5s，给平台留余量）。
_MIN_INTERVAL = float(os.environ.get("BIRDREPORT_MIN_INTERVAL", "2.5"))
_last_call_ts = 0.0


def _rate_limit():
    global _last_call_ts
    now = time.monotonic()
    wait = _MIN_INTERVAL - (now - _last_call_ts)
    if wait > 0:
        time.sleep(wait)
    _last_call_ts = time.monotonic()


def _decrypt_any(b64text):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    ct = base64.b64decode(b64text)
    for k, iv in _KEYS:
        try:
            return json.loads(unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(ct), 16).decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return None


def front_call(path, params_dict):
    """调 Node 助手发签名请求，返回 (code, count, data)。data 已解密为 Python 对象。
    内置速率限制 + 505 退避：触发 505 时 sleep 60s 重试一次，再 505 直接 abort。
    """
    _rate_limit()
    return _front_call_raw(path, params_dict)


def _front_call_raw(path, params_dict, _retry=False):
    # 原样拼接（不 urlencode）：站点 format() 期望原始中文值；鸟类查询值不含 &/=
    params = "&".join(f"{k}={v}" for k, v in params_dict.items())
    payload = json.dumps({"path": path, "params": params})
    try:
        p = subprocess.run(["node", HELPER], input=payload, capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"调用 Node 助手失败: {e}（确认已装 Node + node_modules）\n")
        return None, None, None
    if not p.stdout:
        sys.stderr.write(f"助手无输出，stderr={p.stderr[:200]}\n")
        return None, None, None
    r = json.loads(p.stdout)
    if r.get("error"):
        sys.stderr.write(f"助手错误: {r['error']}\n")
        return None, None, None
    code = r.get("code")
    # 505 多因 limit>50（服务端硬上限，已在 search_public 限到≤50）。
    # 不再 sleep 重试——那会阻塞会话(曾导致 cc-connect 卡死)；直接返回让调用方降级。
    if code == 505:
        sys.stderr.write("birdreport 505（确认 limit≤50；可能瞬时限流）——跳过，不阻塞\n")
    data = r.get("data_raw")
    if isinstance(data, str) and data:
        data = _decrypt_any(data)
    return code, r.get("count"), data


MAX_LIMIT = 50  # 服务端硬上限：limit>50 必 500/505，务必 ≤50（分页取更多）


def region_summary(province, city, district, start, end):
    """区域公开汇总（稳定）：报告数 / 记录数 / 鸟种数。"""
    body = {"startTime": start, "endTime": end, "province": province, "city": city,
            "district": district, "taxonid": "", "pointname": "", "mode": "0", "outside_type": "0"}
    code, _, data = front_call("/front/record/chart/summary", body)
    if code == 0 and isinstance(data, dict):
        return {"reports": data.get("reports_count") or data.get("report_num_1"),
                "records": data.get("record_count") or data.get("record_num_1"),
                "species": data.get("taxon_count") or data.get("taxon_num_1")}
    return None


def region_taxa(province, city, district="", pointname="", start="", end="",
                taxon_month="", version="CH4", pages=8, limit=MAX_LIMIT):
    """公开**鸟种名单**：/front/record/activity/taxon，按 地区/点位 + 时间 聚合。
    返回 [{name, latin, english, taxon_id, recordcount, family, order}]（按 recordcount 降序）。
    ⚠️ 时间务必用 startTime/endTime（年份精确，如 2026-05-01~2026-05-31）。
       taxon_month（仅月份数字）语义有坑——拿不到"今年某月"，留空即可。"""
    limit = min(limit, MAX_LIMIT)
    out = []
    for page in range(1, pages + 1):
        body = {"taxonid": "", "startTime": start, "endTime": end, "province": province,
                "city": city, "district": district, "pointname": pointname, "username": "",
                "serial_id": "", "ctime": "", "version": version, "state": "", "mode": "0",
                "taxon_month": str(taxon_month), "outside_type": "0", "page": page, "limit": limit}
        code, count, rows = front_call("/front/record/activity/taxon", body)
        if code != 0 or not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        if len(rows) < limit:
            break
    species = [{"name": t.get("taxonname"), "latin": t.get("latinname"),
                "english": t.get("englishname"), "taxon_id": t.get("taxon_id"),
                "recordcount": t.get("recordcount"), "family": t.get("taxonfamilyname"),
                "order": t.get("taxonordername")} for t in out if t.get("taxonname")]
    species.sort(key=lambda x: x.get("recordcount") or 0, reverse=True)
    return species


def search_public(province, city, district, start, end, page=1, limit=MAX_LIMIT):
    """公开报告列表（单页，返回 (code,count,rows)）。limit 强制 ≤50（服务端硬上限，>50 必 500/505）。"""
    limit = min(limit, MAX_LIMIT)
    body = {"page": page, "limit": limit, "taxonid": "", "startTime": start, "endTime": end,
            "province": province, "city": city, "district": district, "pointname": "",
            "username": "", "serial_id": "", "ctime": "", "taxonname": "", "state": "",
            "mode": "0", "outside_type": "0"}
    return front_call("/front/record/activity/search", body)


def count_bars(province, city, district, start, end):
    """统计端点 fallback：返回区域月度报告数和鸟种数（粗粒度，不含点位）。"""
    base = {"province": province, "city": city, "district": district,
            "startTime": start, "endTime": end}
    _, _, rep = front_call("/front/record/search/ReportCountBar", dict(base))
    _, _, tax = front_call("/front/record/search/TaxonCountBar", dict(base))
    return rep if isinstance(rep, list) else [], tax if isinstance(tax, list) else []


def fetch_serial_taxa(serial_id):
    """下钻：取某份公开报告里的鸟种列表。
    端点 /front/activity/taxon 尚未在本环境完整验证；首次调用失败会回 (None,..)，
    上层自行决定是否放弃。"""
    code, count, data = front_call("/front/activity/taxon", {"serial_id": serial_id})
    return code, count, data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--province", default="")
    ap.add_argument("--city", default="")
    ap.add_argument("--district", default="")
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--limit", type=int, default=50,
                    help="单页大小（服务端对 >50 会 500，默认 50）")
    ap.add_argument("--pages", type=int, default=3,
                    help="最多拉几页用于聚合热点 Top（默认 3 页）")
    ap.add_argument("--point", default="",
                    help="客户端按 point_name 子串过滤（如 --point 世纪公园）")
    ap.add_argument("--with-taxa", action="store_true",
                    help="对（过滤后）前 --max-taxa 份报告下钻鸟种（慢，礼貌限速）")
    ap.add_argument("--max-taxa", type=int, default=5,
                    help="最多下钻几份报告（默认 5）")
    ap.add_argument("--taxa", action="store_true",
                    help="取公开鸟种名单（用 --start/--end 日期范围，年份精确）")
    ap.add_argument("--taxon-month", default="",
                    help="（不推荐）仅按月份数字查，拿不到今年某月，留空即可")
    ap.add_argument("--pointname", default="",
                    help="服务端按观测点名过滤（如 上海植物园）")
    args = ap.parse_args()

    # 模式 A：公开鸟种名单 —— "区域有哪些鸟"的来源。用 startTime/endTime 日期范围（年份精确）。
    if args.taxa or args.taxon_month:
        sp = region_taxa(args.province, args.city, args.district, args.pointname,
                         start=args.start, end=args.end, taxon_month=args.taxon_month)
        print(json.dumps({
            "source": "中国观鸟记录中心（公开鸟种名单 /front/record/activity/taxon）",
            "filter": {"province": args.province, "city": args.city,
                       "pointname": args.pointname or None,
                       "window": f"{args.start}~{args.end}" if args.start else None,
                       "taxon_month": args.taxon_month or None},
            "species_count": len(sp),
            "species": sp,
        }, ensure_ascii=False, indent=2))
        return

    all_rows = []
    total_count = 0
    for page in range(1, args.pages + 1):
        code, count, rows = search_public(args.province, args.city, args.district,
                                          args.start, args.end,
                                          page=page, limit=args.limit)
        if code != 0 or not isinstance(rows, list):
            break
        total_count = count or total_count
        all_rows.extend(rows)
        if len(rows) < args.limit:
            break  # 已是最后一页
        # 不再额外 sleep：front_call 已内置 _MIN_INTERVAL（默认 2.5s）

    if all_rows:
        # 客户端点位过滤（推荐路径：避免刺激服务端 pointname 校验）
        filtered = all_rows
        if args.point:
            filtered = [r for r in all_rows if args.point in (r.get("point_name") or "")]

        points = {}
        for c in filtered:
            nm = c.get("point_name")
            if nm:
                points[nm] = points.get(nm, 0) + 1

        result = {
            "source": "中国观鸟记录中心（公开数据 /front/activity/search）",
            "total_public_checklists": total_count,
            "fetched": len(all_rows),
            "pages_fetched": min(args.pages, (len(all_rows) + args.limit - 1) // args.limit),
            "filter_point": args.point or None,
            "filtered_count": len(filtered) if args.point else None,
            "top_points": sorted(points.items(), key=lambda x: x[1], reverse=True)[:15],
            "recent": [{"point": c.get("point_name"), "district": c.get("district_name"),
                        "start_time": c.get("start_time"), "serial_id": c.get("serial_id")}
                       for c in filtered[:15]],
        }

        if args.with_taxa and filtered:
            targets = filtered[: args.max_taxa]
            taxa_results = []
            for c in targets:
                sid = c.get("serial_id")
                if not sid:
                    continue
                code, _, data = fetch_serial_taxa(sid)
                if code == 0 and isinstance(data, list):
                    names = []
                    for t in data:
                        n = (t.get("taxon_name") or t.get("taxonName")
                             or t.get("name") or t.get("cn_name"))
                        if n:
                            names.append(n)
                    taxa_results.append({"serial_id": sid, "point": c.get("point_name"),
                                         "start_time": c.get("start_time"),
                                         "taxa_count": len(names), "taxa": names})
                else:
                    taxa_results.append({"serial_id": sid, "point": c.get("point_name"),
                                         "error": f"taxon code={code}"})
            result["taxa_drilldown"] = taxa_results

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Fallback：activity/search 端点偶发 500 时，退化到 CountBar 统计端点
    rep, tax = count_bars(args.province, args.city, args.district, args.start, args.end)
    if not rep and not tax:
        print(json.dumps({"source": "中国观鸟记录中心(公开)", "checklists": 0,
                          "note": "未获取到公开记录或接口失败"}, ensure_ascii=False))
        return
    total_reports = sum(r.get("reports_count", 0) for r in rep)
    total_domestic = sum(r.get("report_num_1", 0) for r in rep)
    total_overseas = sum(r.get("report_num_2", 0) for r in rep)
    monthly = [{"month": r.get("taxon_month"),
                "reports": r.get("reports_count"),
                "domestic": r.get("report_num_1"),
                "overseas": r.get("report_num_2"),
                "taxa_total": next((t.get("taxon_count") for t in tax
                                    if t.get("taxon_month") == r.get("taxon_month")), None)}
               for r in rep]
    print(json.dumps({
        "source": "中国观鸟记录中心（公开数据 /front/CountBar，fallback）",
        "note": "/front/record/activity/search 当前服务端返回 500，已降级到统计端点；"
                "粗粒度：仅区域级月度合计，不含点位。",
        "window": f"{args.start} ~ {args.end}",
        "total_public_checklists": total_reports,
        "domestic_checklists": total_domestic,
        "overseas_checklists": total_overseas,
        "monthly": monthly,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
