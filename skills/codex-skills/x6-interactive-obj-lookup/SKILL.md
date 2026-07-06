---
name: x6-interactive-obj-lookup
description: X6Game交互物信息查询。Use when Codex needs to find SceneObj/交互物 ObjID, name, BP path, or related map spawners from X6 config tables; supports keyword search, BP path/name fuzzy search, ID-to-name lookup, and ObjID-to-spawner lookup in workspaces with DesignerConfigurations/obj and DesignerConfigs/map/spawners.
---

# X6 Interactive Object Lookup

Use this skill to answer questions like:

- "`BP_FishLightQueue` 对应哪个 ObjID?"
- "`208784` 是什么交互物?"
- "模糊搜一下鱼灯相关交互物"
- "这个 ObjID 被哪些 spawner 使用?"

## Workflow

1. Confirm the current workspace is an X6Game workspace with `X6Game/DesignerConfigurations/obj`.
2. Run the bundled script first:

```powershell
python C:\Users\banqiang\.codex\skills\x6-interactive-obj-lookup\scripts\query_interactive_obj.py "BP_FishLightQueue" --workspace .
```

3. For an exact ID lookup, pass the ID directly:

```powershell
python C:\Users\banqiang\.codex\skills\x6-interactive-obj-lookup\scripts\query_interactive_obj.py 208784 --workspace .
```

4. To include `TbSpawner` rows whose `obj_id` matches the found ObjID(s), add `--with-spawners`:

```powershell
python C:\Users\banqiang\.codex\skills\x6-interactive-obj-lookup\scripts\query_interactive_obj.py "鱼灯" --workspace . --with-spawners
```

5. If the script output is too broad, rerun with `--limit <n>` or use a more specific keyword/BP name.

## Data Sources

The script reads, in order:

- Scene object export text files under `X6Game/DesignerConfigurations/obj/场景对象表/DontDeleteMe/*.txt`
- Scene object Excel files under `X6Game/DesignerConfigurations/obj/场景对象表/*.xlsx` when text exports are absent
- Spawner Excel files under `X6Game/DesignerConfigs/map/spawners/spawner/*.xlsx` when `--with-spawners` is requested

Important table definitions:

- `obj.TbSceneObj`: `X6Game/DesignerConfigurations/CfgDefinitions/obj.xml`
- `map.TbSpawner`: `X6Game/DesignerConfigs/CfgDefines/map.xml`

## Reporting

Report the ObjID,交互物名, BP path, source file, and source row when available. When reporting spawners, include `spawner_id`, `datalayer_id`, `name`, `position`, and source file/row.

If there are no hits, say which source roots were searched and suggest checking whether the BP is absent from `TbSceneObj`, appears only in generated resources, or uses a different BP path/name.
