#!/usr/bin/env python3
"""一次性清理:把 Base 里已经存在但应被新过滤规则刷掉的记录,标记为状态=已忽略。

复用 fetch.py 的过滤规则(MIN_DURATION_SEC + NON_DEV_TITLE_PATTERNS)。
不删除记录,只更新状态字段,保留追溯。
"""
import json
import sys
from pathlib import Path

# 复用 fetch.py 的常量与工具
sys.path.insert(0, str(Path(__file__).parent))
from fetch import (  # noqa: E402
    BASE_TOKEN,
    TABLE_ID,
    MIN_DURATION_SEC,
    is_dev_relevant,
    log,
    run_lark_cli,
)


def parse_display_duration(s):
    """Convert display duration (e.g. '12:34' or '1:23:45') back to seconds."""
    if not s:
        return 0
    parts = s.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def fetch_all_records():
    """Returns list of (record_id, video_id, duration_str, title, current_status)."""
    out = []
    offset = 0
    limit = 200
    while True:
        proc = run_lark_cli(
            [
                "base",
                "+record-list",
                "--base-token",
                BASE_TOKEN,
                "--table-id",
                TABLE_ID,
                "--field-id",
                "视频ID",
                "--field-id",
                "时长",
                "--field-id",
                "英文标题",
                "--field-id",
                "状态",
                "--limit",
                str(limit),
                "--offset",
                str(offset),
                "--format",
                "json",
                "--as",
                "user",
            ]
        )
        if proc.returncode != 0:
            log(f"读取 Base 失败\n{proc.stderr or proc.stdout}")
            return out
        envelope = json.loads(proc.stdout)
        data_obj = envelope.get("data") or {}
        rows = data_obj.get("data") or []
        fields = data_obj.get("fields") or []
        record_ids = data_obj.get("record_id_list") or []
        if not rows:
            break

        def col(name):
            try:
                return fields.index(name)
            except ValueError:
                return -1

        i_vid = col("视频ID")
        i_dur = col("时长")
        i_tit = col("英文标题")
        i_sta = col("状态")

        def cell(row, idx):
            if idx < 0 or idx >= len(row):
                return ""
            v = row[idx]
            if v is None:
                return ""
            if isinstance(v, str):
                return v
            if isinstance(v, list):
                if not v:
                    return ""
                if isinstance(v[0], str):
                    return v[0]  # select 单选
                if isinstance(v[0], dict):
                    return "".join(
                        seg.get("text", "") or seg.get("name", "")
                        for seg in v
                        if isinstance(seg, dict)
                    )
            return str(v)

        for rid, row in zip(record_ids, rows):
            out.append(
                (
                    rid,
                    cell(row, i_vid),
                    cell(row, i_dur),
                    cell(row, i_tit),
                    cell(row, i_sta),
                )
            )

        if not data_obj.get("has_more") or len(rows) < limit:
            break
        offset += limit
    return out


def batch_mark_ignored(record_ids):
    if not record_ids:
        return 0
    # 分批避免命令行长度问题(虽然 batch-update 只是一组 IDs + 一个 patch,通常不会超长)
    written = 0
    chunk = 200
    for i in range(0, len(record_ids), chunk):
        ids = record_ids[i : i + chunk]
        payload = {"record_id_list": ids, "patch": {"状态": "已忽略"}}
        proc = run_lark_cli(
            [
                "base",
                "+record-batch-update",
                "--base-token",
                BASE_TOKEN,
                "--table-id",
                TABLE_ID,
                "--json",
                json.dumps(payload, ensure_ascii=False),
                "--as",
                "user",
            ]
        )
        if proc.returncode != 0:
            log(f"批量更新第 {i // chunk + 1} 批失败\n{proc.stderr or proc.stdout}")
            continue
        written += len(ids)
    return written


def main():
    records = fetch_all_records()
    log(f"Base 共 {len(records)} 条记录")

    to_ignore = []
    for rid, vid, dur_str, title, status in records:
        if status == "已忽略":
            continue  # 已经标记过的跳过
        sec = parse_display_duration(dur_str)
        if 0 < sec < MIN_DURATION_SEC:
            to_ignore.append((rid, f"短<{MIN_DURATION_SEC // 60}min ({dur_str})", title))
            continue
        if not is_dev_relevant(title):
            to_ignore.append((rid, "非开发标题", title))
            continue

    log(f"识别到 {len(to_ignore)} 条该刷成「已忽略」")
    for rid, reason, title in to_ignore:
        log(f"  [{reason}] {title[:70]}")

    if not to_ignore:
        log("无需清理")
        return

    written = batch_mark_ignored([t[0] for t in to_ignore])
    log(f"完成: {written}/{len(to_ignore)} 条状态已改为「已忽略」")


if __name__ == "__main__":
    main()
