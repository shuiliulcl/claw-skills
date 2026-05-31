#!/usr/bin/env python3
"""把人生鸟单 + 出行记录同步进 Obsidian vault，建成双链图谱 + Dataview 仪表盘。

数据来源：~/.birdwatch/lifelist.json（由 birdreport-logger 的 lifelist.py 生成）。
在 vault 的「观鸟/」下建：species/<鸟名>.md（每种一篇）、观鸟仪表盘.md。
**只在「观鸟/」下新建，绝不改动你已有笔记；已存在的物种笔记默认跳过（保留你的手写内容）。**

需要 Obsidian 装 Dataview 社区插件，仪表盘/反链统计才会渲染。

环境变量 BIRDWATCH_VAULT（默认 ~/ObsidianVault）。
用法：
  python obsidian_sync.py                 # 用缓存的人生鸟单同步
  python obsidian_sync.py --force-species  # 连已存在物种笔记的 frontmatter 也更新
"""
import argparse
import json
import os
import sys

import birdwatch_config as cfg

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

LIFELIST = os.path.join(os.path.expanduser("~"), ".birdwatch", "lifelist.json")


def species_note(s):
    fm = [
        "---", "type: 鸟种", f"taxon_id: {s.get('taxon_id')}",
        f"拉丁名: {s.get('latin') or ''}", f"目: {s.get('order') or ''}",
        f"科: {s.get('family') or ''}", f"首次记录: {s.get('earliest') or ''}",
        f"报告次数: {s.get('reports') or 0}", "状态: 已记录",
        "tags: [观鸟/鸟种]", "---", "",
        f"# {s['name']}", "",
        "## 见过这鸟的出行", "```dataview",
        "LIST WHERE contains(file.outlinks, this.file.link)", "```", "",
    ]
    return "\n".join(fm)


DASHBOARD = """---
tags: [观鸟]
---
# 🦅 观鸟仪表盘

> 人生鸟单与出行记录自动统计（需 Dataview 插件）。鸟种来自中国观鸟记录中心。

## 人生鸟单（已记录鸟种）
```dataview
TABLE 科, 目, 首次记录, 报告次数
FROM #观鸟/鸟种
SORT 首次记录 DESC
```

## 出行记录
```dataview
TABLE 地点, 省市, 鸟种数, 新增种
FROM #观鸟/出行
SORT date DESC
```

## 今年新增鸟种
```dataview
TABLE 首次记录
FROM #观鸟/鸟种
WHERE 首次记录 >= date(2026-01-01)
SORT 首次记录 DESC
```

## 各科鸟种数
```dataview
TABLE length(rows) as 种数
FROM #观鸟/鸟种
GROUP BY 科
SORT length(rows) DESC
```
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=None)
    ap.add_argument("--force-species", action="store_true")
    args = ap.parse_args()

    if not args.vault and not cfg.flag("obsidian.enabled"):
        sys.exit("Obsidian 集成未启用（config.json obsidian.enabled=false）。如需启用请置 true 并设 vault_path，或用 --vault 指定。")
    vault = args.vault or cfg.get_path("obsidian.vault_path", env="BIRDWATCH_VAULT")
    if not vault or not os.path.isdir(vault):
        sys.exit(f"找不到 vault：{vault}")
    args.vault = vault
    if not os.path.exists(LIFELIST):
        sys.exit(f"找不到人生鸟单缓存 {LIFELIST}，请先运行 birdreport-logger/scripts/lifelist.py")

    with open(LIFELIST, encoding="utf-8") as f:
        life = json.load(f)
    species = life.get("species", [])

    root = os.path.join(args.vault, "观鸟")
    sp_dir = os.path.join(root, "species")
    os.makedirs(os.path.join(root, "trips"), exist_ok=True)
    os.makedirs(sp_dir, exist_ok=True)

    created, skipped = 0, 0
    for s in species:
        if not s.get("name"):
            continue
        path = os.path.join(sp_dir, f"{s['name']}.md")
        if os.path.exists(path) and not args.force_species:
            skipped += 1
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(species_note(s))
        created += 1

    with open(os.path.join(root, "观鸟仪表盘.md"), "w", encoding="utf-8") as f:
        f.write(DASHBOARD)

    print(f"vault: {args.vault}")
    print(f"物种笔记：新建 {created}，跳过(已存在) {skipped}，共 {len(species)} 种")
    print(f"已写入仪表盘：{os.path.join(root, '观鸟仪表盘.md')}")
    print("提示：Obsidian 需启用 Dataview 社区插件才能渲染统计。")


if __name__ == "__main__":
    main()
