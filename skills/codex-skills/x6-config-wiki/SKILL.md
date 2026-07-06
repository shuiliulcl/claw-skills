---
name: x6-config-wiki
description: "X6Game configuration knowledge and lookup workflow. Use when reading, modifying, reviewing, or explaining X6 config data, XML definitions, DesignerConfigs/DesignerConfigurations, CfgDefines/CfgDefinitions, Excel/DT/DA export, genserver/gen_all/gen_client_cfg, GenV2 CfgTypes.lua, PaperEnum.Cfg.*, self:GetDataCfg().TbXxx,导表/打表/配置检查/版本号/Tag/multi_rows, or when Lua code depends on generated config tables or enums."
---

# X6 Config Wiki

## Core Rule

Treat X6 config as a source chain, not a single file:

`root.xml -> CfgDefinitions/CfgDefines XML -> Excel/DT/DA data source -> genserver -> GenV2/*/Cfg/CfgTypes.lua + config_output(_new) -> PaperDataMgr -> PaperEnum.Cfg / self:GetDataCfg()`

When answering or changing config-related Lua, verify the chain from source XML and generated output before assuming enum names, table names, field types, or version behavior.

Submission convention: generated Lua/data outputs such as `X6Game/Content/Script/GenV2/**/Cfg/CfgTypes.lua`, `CfgHelper.lua`, and `config_output(_new)` are normally not submitted with ordinary feature CLs unless the user or branch workflow explicitly says to include generated artifacts. During review, do not treat missing generated `CfgTypes.lua` as a default submit blocker; verify the XML/source definition and runtime references, then mention local generation or submit-order risk only when it matters.

## Fast Paths

- **Find enum source**: search `X6Game/DesignerConfigurations/CfgDefinitions` first. Shared enums such as `aitask.EAITaskType` live there.
- **Find table/bean/input source**: search `X6Game/DesignerConfigs/CfgDefines` for `<table name=...>`, `<bean name=...>`, and `input=...`.
- **Find generated Lua type**: search `X6Game/Content/Script/GenV2/<major>_<minor>/Cfg/CfgTypes.lua`.
- **Find runtime Lua use**: search `X6Game/Content/Script` for `PaperEnum.Cfg.<module>`, `self:GetDataCfg().TbXxx`, and table/enum names.
- **Find generation command**: read `X6Game/BatchFiles/gen_client_cfg.bat` and `X6Game/BatchFiles/gen_all.py`; do not invent parameters.
- **Find Excel index/sheet mapping**: use the XML `input` attribute first; `PaperExcelOverviewer` can also show/derive Sheet and index information from `CfgDefines`.

## Local Sources

Key paths in the current workspace:

- `X6Game/DesignerConfigs/CfgDefines/root.xml`: top-level config root. It imports both `../../DesignerConfigurations/CfgDefinitions/` and `.`.
- `X6Game/DesignerConfigurations/CfgDefinitions/*.xml`: shared XML definitions, usually hand-maintained and shared across branches.
- `X6Game/DesignerConfigs/CfgDefines/*.xml`: branch-specific XML, often generated/exported by tools; usually defines `bean`, `table`, and `input`.
- `X6Game/DesignerConfigs/**`: primary generated or branch-specific config data source directory.
- `X6Game/DesignerConfigurations/**`: shared design config data and shared XML definitions.
- `Tools/Gen/CppGen/win/genserver.exe`: Gen executable.
- `Tools/Gen/CppGen/tpl/cfg/lua_cfg_types*.tpl`: Lua `CfgTypes.lua` templates.
- `X6Game/Content/Script/GenV2/<version>/Cfg/CfgTypes.lua`: generated Lua cfgtypes.
- `X6Game/Content/config_output_new` or `X6Game/Content/config_output`: generated client config data.
- `X6Game/Content/Script/PaperLuaFramework/Data/PaperDataMgr.lua`: loads generated config types/data and merges generated enums into `PaperEnum.Cfg`.

## Workflows

### Trace a Config Field or Table

1. Search XML definitions:
   - `rg -n "<table name=\"TbXxx\"|<bean name=\"BeanXxx\"|field_name|input=" X6Game/DesignerConfigs/CfgDefines X6Game/DesignerConfigurations/CfgDefinitions`
2. Confirm whether the source is shared or branch-specific:
   - Shared enum/const/schema: `DesignerConfigurations/CfgDefinitions`.
   - Branch table/input: `DesignerConfigs/CfgDefines`.
3. Read the `<table>` declaration:
   - `name` is runtime table name.
   - `value` is row bean type.
   - `input` points to Excel/JSON/XML/Lua/directory data source.
   - `index` overrides key field; when missing, the first bean field is usually the key.
4. Search generated output:
   - `rg -n "cfg.<module>.<Bean>|<module>.<Enum>|TbXxx" X6Game/Content/Script/GenV2/<version>/Cfg/CfgTypes.lua`
5. Search runtime readers:
   - `rg -n "PaperEnum.Cfg.<module>|GetDataCfg\\(\\)\\.TbXxx|TbXxx" X6Game/Content/Script`

### Trace an Enum Used by Lua

1. Search `DesignerConfigurations/CfgDefinitions/<module>.xml`.
2. Confirm generated `CfgTypes.lua` contains the exact enum member.
3. Confirm Lua references use the generated name exactly.
4. If old/new names disagree, treat generated `CfgTypes.lua` plus source XML as authoritative, then inspect local Lua references for stale names.

Example: `aitask.EAITaskType` source is `X6Game/DesignerConfigurations/CfgDefinitions/aitask.xml`; the branch-specific `X6Game/DesignerConfigs/CfgDefines/aitask.xml` only defines `TaskGroupTypeRule` and `Tb_DT_TaskGroupType`.

### Trace XML to Excel or DT/DA Export

Do not assume every flow is XML -> Excel:

- Normal runtime config flow is `XML schema + Excel data -> generated bin/Lua types`.
- DT/DA/editor export flows may use XML schema to parse/export editor data into Excel. For these, inspect feature-specific tools/docs and the XML field definitions.
- `PaperExcelOverviewer` reads `CfgDefines/*.xml` to map Excel path, Sheet, Bean, index, and `ref`; it is an overview/indexing helper, not the general config generator.
- When removing hidden Excel workbook settings such as data validation, comments, conditional formatting, defined names, tables, filters, or protection, do not rewrite worksheet XML with generic XML serializers such as Python `ElementTree`. They may rename Excel namespace prefixes (`mc`, `x14ac`, `xr`, `xr2`, `xr3`, `r`) while leaving references like `mc:Ignorable` semantically inconsistent, causing Excel repair dialogs. Prefer Excel/openpyxl high-level APIs when full workbook rewrite is acceptable; for minimal binary-safe edits, remove the exact OOXML node text from the zipped `.xlsx` while preserving the original namespace declarations and surrounding XML.

### Verify Generation Commands

Use existing scripts as source of truth:

- `X6Game/BatchFiles/gen_client_cfg.bat` calls `genserver -j config -d DesignerConfigs/CfgDefines/root.xml --inputdatadir DesignerConfigs --extradirs <workspace> --outputcodedir Content/Script/GenV2/<version>/Cfg --outputdatadir Content/config_output -t client -l lua --tpl Tools/Gen/CppGen ...`
- `X6Game/BatchFiles/gen_all.py` is the broader PPL/local generation workflow; it writes versioned `GenV2/<major>_<minor>/Cfg` and `config_output_new`.
- `genserver.exe --help` is cheap and should be used before quoting flags.

Never run destructive P4 operations. If generating or editing config files, follow project `AGENTS.md` P4 rules first.

## X6 Config Semantics

- `topmodule` in `root.xml` sets the top namespace, usually `cfg`.
- `<module name="xxx">` maps to `cfg.xxx` and generated Lua names such as `cfg.xxx.Bean` / `xxx.Enum`.
- `<enum>` generates `PaperEnum.Cfg.<module>.<EnumName>.<Member>` after `PaperDataMgr` merges generated enums.
- `<bean>` defines row/object structure; nested beans are polymorphic variants.
- `<table>` defines a runtime table and its data source.
- `input="Sheet@path/to/file.xlsx"` pins a Sheet. Multiple inputs can be comma-separated. A directory input reads compatible files under that directory.
- `group="c"` / `group="s"` controls client/server export at field or table level.
- `ref="module.TbTable"` validates config references.
- `path="ue"` / `path="ue?"` validates UE resource path; `res` participates in resource collection.
- `sep` controls compact cell parsing for list/set/map/bean containers.
- `multi_rows` means container data may span rows; Excel effective data rows and merged headers matter.
- Nullable primitive types use `xxx?` and require explicit `null` in config.

## Version and Export Column Rules

For导表列/打表 behavior, read the Lark doc in `references/lark-docs.md` before giving detailed rules. Core reminders:

- Empty导表列 normally exports by default.
- `否` / `FALSE` means do not export.
- `Test$version`, `Test`, and `测试` depend on `--exporttestdata`.
- When generating with `--version`, version/tag priority changes.
- `multi_rows:true` has special version-row behavior.

## Lark Docs

When local source is insufficient or the task asks for docs/background, search or fetch the docs listed in `references/lark-docs.md`. Prefer local source for current branch truth, and use Lark docs for rules, concepts, and historical intent.
