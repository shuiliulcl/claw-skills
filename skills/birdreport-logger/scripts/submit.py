#!/usr/bin/env python3
"""birdreport.cn 个人观鸟记录快速提交 —— 把极简模板映射成平台提交。

设计目标：你只填「日期/地点/时段/鸟种+数量」，脚本自动补全平台要的一堆冗余字段、
解析鸟种名→taxon_id、点位→完整点对象，然后提交。

【安全】只提交你真实观测的数据。默认 dry-run 只打印将提交的内容，
加 --submit 才真正发送。不提交任何编造/测试数据。

流程（已逆向自网页版）：
  1) POST /member/system/activity/saveReport  建活动 → 返回 activity_id
  2) POST /member/system/record/push          每个鸟种调一次
响应 data 为 AES-256-CBC(base64)，key/iv 取自站点 aes.util.js。

环境变量：
  BIRDREPORT_TOKEN       登录后浏览器 DevTools 复制的 X-Auth-Token（会过期）
  BIRDREPORT_MEMBER_ID   你的 member_id（数字）

用法：
  python submit.py 记录.txt              # dry-run，打印将提交内容
  python submit.py 记录.txt --submit     # 确认无误后真正提交
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import uuid
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
HERE = os.path.dirname(os.path.abspath(__file__))
TAXONOMY = os.path.join(HERE, "taxonomy.json")


def headers():
    token = cfg.get("birdreport.token", env="BIRDREPORT_TOKEN")
    if not token:
        sys.exit("缺少 birdreport.token（config.json 或 env）；可用 grab_token.py 获取")
    return {
        "Content-Type": "application/json", "X-Auth-Token": token,
        "Origin": "https://www.birdreport.cn", "Referer": "https://www.birdreport.cn/",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    }


def api(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                 headers=headers(), method="POST")
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"接口 {path} HTTP {e.code}（401/403 多为 token 失效，请重新登录复制）")
    if payload.get("code") not in (0, "0"):
        sys.exit(f"接口 {path} 返回错误: {json.dumps(payload, ensure_ascii=False)[:200]}")
    data = payload.get("data")
    if isinstance(data, str) and data:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        ct = base64.b64decode(data)
        return json.loads(unpad(AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(ct), 16).decode("utf-8"))
    return data


# ---------- 模板解析 ----------
def parse_template(path):
    """极简格式：key: value 行 + 「鸟种:」后每行 '名字 数量' 或 '名字: 数量'。"""
    rec = {"birds": []}
    in_birds = False
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#")[0].rstrip()
            if not line.strip():
                continue
            if re.match(r"^\s*(鸟种|物种|birds)\s*[:：]\s*$", line):
                in_birds = True
                continue
            if in_birds:
                m = re.match(r"^\s*(.+?)[\s:：]+(\d+)\s*$", line)
                if m:
                    rec["birds"].append((m.group(1).strip(), int(m.group(2))))
                continue
            m = re.match(r"^\s*([^:：]+)[:：]\s*(.*)$", line)
            if m:
                rec[m.group(1).strip()] = m.group(2).strip()
    return rec


def get(rec, *keys, default=""):
    for k in keys:
        if k in rec and rec[k] != "":
            return rec[k]
    return default


# ---------- 解析时段 ----------
def parse_times(date, span):
    """'07:00-09:00' + 日期 → (start,end) 完整时间串。"""
    m = re.match(r"\s*(\d{1,2}:\d{2})\s*[-~到至]\s*(\d{1,2}:\d{2})\s*", span)
    if not m:
        sys.exit(f"时段格式无法识别: {span!r}（应如 07:00-09:00）")
    s, e = m.group(1), m.group(2)
    fix = lambda t: (("0" + t) if len(t) == 4 else t) + ":00"
    return f"{date} {fix(s)}", f"{date} {fix(e)}"


# ---------- 鸟种解析 ----------
def load_taxonomy():
    with open(TAXONOMY, "r", encoding="utf-8") as f:
        rows = json.load(f)
    by_name, by_py, by_szm = {}, {}, {}
    for r in rows:
        by_name[r["name"]] = r
        by_py.setdefault(r.get("pinyin"), r)
        by_szm.setdefault(r.get("szm"), r)
    return by_name, by_py, by_szm


def resolve_bird(token, by_name, by_py, by_szm):
    if token in by_name:
        return by_name[token]
    t = token.lower()
    if t in by_py:
        return by_py[t]
    if t in by_szm:
        return by_szm[t]
    return None


# ---------- 点位解析 ----------
def resolve_point(spot):
    """spot 为数字→直接取 point_id 详情；为名字→point/list 模糊找候选。"""
    if str(spot).isdigit():
        p = api("/member/system/point/get", {"point_id": int(spot)})
        if not isinstance(p, dict):
            sys.exit(f"point_id={spot} 查不到点位详情")
        return p, []
    rows = api("/member/system/point/list", {"page": 1, "limit": 20, "point_name": spot}) or []
    exact = [r for r in rows if r.get("point_name") == spot]
    cands = exact or rows
    if len(cands) == 1:
        # point/list 的记录字段较全，但 saveReport 需要标准点对象，按 id 再取一次
        return api("/member/system/point/get", {"point_id": cands[0]["point_id"]}), []
    return None, cands[:10]


def build_point_obj(p, member_id):
    return {
        "point_id": str(p.get("point_id")), "point_name": p.get("point_name"),
        "province_name": p.get("province_name"), "city_name": p.get("city_name"),
        "district_name": p.get("district_name"), "adcode": str(p.get("adcode") or ""),
        "longitude": str(p.get("longitude") or ""), "latitude": str(p.get("latitude") or ""),
        "altitude": str(p.get("altitude") or ""), "member_id": member_id, "isopen": 0,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("template", help="记录模板文件路径")
    ap.add_argument("--submit", action="store_true", help="真正提交（默认仅 dry-run 预览）")
    args = ap.parse_args()

    member_id = cfg.get("birdreport.member_id", env="BIRDREPORT_MEMBER_ID")
    if not member_id:
        sys.exit("缺少 birdreport.member_id（config.json 或 env）")
    member_id = int(member_id)

    rec = parse_template(args.template)
    date = get(rec, "日期", "date")
    spot = get(rec, "地点", "point", "观测点")
    span = get(rec, "时段", "时间", "time")
    note = get(rec, "备注", "笔记", "note")
    keywords = get(rec, "关键字", "keywords")
    if not (date and spot and span and rec["birds"]):
        sys.exit("模板缺少必填项：日期 / 地点 / 时段 / 鸟种")

    start, end = parse_times(date, span)

    # 解析点位
    point, cands = resolve_point(spot)
    if point is None:
        msg = "地点无法唯一确定，请在模板「地点」直接填 point_id。候选：\n"
        for c in cands:
            msg += f"  {c.get('point_id')}  {c.get('point_name')} ({c.get('province_name')}{c.get('district_name')})\n"
        sys.exit(msg)
    point_obj = build_point_obj(point, member_id)

    # 解析鸟种
    by_name, by_py, by_szm = load_taxonomy()
    resolved, unknown = [], []
    for name, count in rec["birds"]:
        t = resolve_bird(name, by_name, by_py, by_szm)
        if t:
            resolved.append((t["name"], t["taxon_id"], count))
        else:
            unknown.append(name)
    if unknown:
        sys.exit("以下鸟种名未匹配（请用准确中文名/拼音/首字母）：" + "、".join(unknown))

    # 预览
    print("=" * 50)
    print(f"观测点  : {point_obj['point_name']}（id={point_obj['point_id']}, "
          f"{point_obj['province_name']}{point_obj['district_name']}）")
    print(f"时段    : {start}  →  {end}")
    print(f"备注    : {note or '(空)'}")
    print(f"鸟种({len(resolved)}):")
    for nm, tid, cnt in resolved:
        print(f"   {nm}  ×{cnt}   (taxon_id={tid})")
    print("=" * 50)

    if not args.submit:
        print("【DRY-RUN】以上为将提交内容，未发送。确认无误后加 --submit 真正提交。")
        return

    # 1) 建活动
    save_body = {
        "point": point_obj,
        "activity": {"id": "", "start_time": start, "end_time": end, "state": "1",
                     "note": note, "keywords": keywords, "domain_type": 0, "member_id": member_id},
        "units_activity": [],
    }
    res = api("/member/system/activity/saveReport", save_body)
    activity_id = res.get("activity_id") or res.get("id") if isinstance(res, dict) else None
    if not activity_id:
        sys.exit(f"建活动失败，未取到 activity_id，返回：{json.dumps(res, ensure_ascii=False)[:200]}")
    print(f"✓ 已建活动 activity_id={activity_id}")

    # 2) 逐鸟种 push
    ok = 0
    for nm, tid, cnt in resolved:
        body = {
            "uuid": str(uuid.uuid4()), "type": 1, "activity_id": str(activity_id),
            "point_id": point_obj["point_id"], "taxon_id": tid, "taxon_name": nm,
            "taxon_count": str(cnt), "member_id": member_id, "note": "",
            "ctime": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        api("/member/system/record/push", body)
        ok += 1
        print(f"  ✓ {nm} ×{cnt}")
        time.sleep(0.4)  # 礼貌限速
    print(f"完成：活动 {activity_id}，提交 {ok} 个鸟种。请到网页/小程序核对。")


if __name__ == "__main__":
    main()
