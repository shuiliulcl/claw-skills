---
name: x6-find-item-id
description: "Find X6Game item IDs from local config sources. Use when the user asks for a 道具ID/item id by item name, display name, item function, func_type, consumable prop name, screenshot text from item config tables, or asks questions like “查一下某某道具的ID”, “这个道具功能对应哪些ID”, “滴滴打鸟ID是多少”."
---

# X6 Find Item ID

## Overview

Look up X6 item IDs from the source config chain instead of guessing. Prefer the workbook or text export under `X6Game/DesignerConfigurations/item` or `X6Game/DesignerConfigs/item`, then cite the exact file, sheet, row, and matched column in the answer.

## Quick Workflow

1. Start with the user's exact keyword from text or screenshot, preserving Chinese punctuation and spacing.
2. Run `scripts/find_item_id.py` from this skill against the current X6 workspace:

```powershell
python <skill-dir>\scripts\find_item_id.py --workspace <workspace-root> "<keyword>"
```

3. If the keyword is a feature/function name such as `滴滴打鸟`, prioritize hits where `func_type` or `道具使用功能类型` matches, then report all matching `id` values.
4. If the keyword is an item display name, prioritize rows where `display_name`, `道具名称`, `name`, or `ItemName_` matches, then report the row `id`.
5. If multiple rows match, keep meaningful distinctions such as normal vs unlimited tickets, version, item type, display name, or function target.

## Config Sources

Use focused item config paths before broader searches:

- `X6Game/DesignerConfigurations/item/**/*.xlsx`
- `X6Game/DesignerConfigurations/item/**/DontDeleteMe/*.txt`
- `X6Game/DesignerConfigs/item/**/*.xlsx`
- `X6Game/DesignerConfigs/item/**/DontDeleteMe/*.txt`

For item-use/function lookups, `TbItemUse` is defined in `X6Game/DesignerConfigurations/CfgDefinitions/item.xml` with input `item/消耗道具表/消耗道具表.xlsx`; its key is `id`.

## Fallback Search

If the script cannot find a result:

- Search the focused item directories with `rg -n -F "<keyword>" ... -j 1`.
- Search `X6Game/DesignerConfigurations/CfgDefinitions/item.xml` for the relevant table definition and input path.
- Search generated runtime config only after source workbooks/text exports fail.
- Do not broaden into all `DesignerConfigurations` or all `DesignerConfigs` unless the user asks or the focused item paths fail.

## Answer Format

Answer with the ID(s), the item/function name that matched, and the source location. Keep it short unless the user asks for the full row.
