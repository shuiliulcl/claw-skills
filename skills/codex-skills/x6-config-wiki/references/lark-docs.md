# Lark Docs For X6 Config

Use these docs when the task needs background, rules, or confirmation beyond the local workspace.

## Gen XML And Config System

- Title: `Gen-数据配置xml说明文档`
- Token: `[redacted]`
- URL: `[redacted internal wiki URL]`
- Use for: Gen concepts, `root.xml`, `topmodule`, `module`, `bean`, `table`, `input`, `index`, `group`, basic/container/nullable types, Excel/json/xml/lua/directory data sources, polymorphic beans, `multi_rows`, `sep`, `ref`, `path`, and `res`.

Important points from the doc:

- `DesignerConfigs/CfgDefines/*.xml` are branch-specific XML files, often generated/exported by tools.
- `DesignerConfigurations/CfgDefinitions/*.xml` are shared XML files, usually hand-maintained.
- `root.xml` imports XML directories and defines top namespace, groups, and services.
- Normal table flow is XML schema plus data source into generated data/code; Excel is the most common data source, but not the only one.

## 导表列, Version, Tag, TEST

- Title: `导表列配置&打表生效说明`
- Token: `[redacted]`
- URL: `[redacted internal wiki URL]`
- Use for: 导表列 behavior, version/tag selection, `--exporttestdata`, `Test$version`, `multi_rows` version behavior, and打表 script context.

Important points from the doc:

- Empty导表列 exports by default.
- `否` or `FALSE` does not export.
- With a specified export version, exact or nearest lower version wins; higher-only versions do not export.
- Without a specified export version, max version wins over empty.
- Test data only exports when test data export is enabled.
- `gen_all.py` and `gen_client_cfg.bat` are named as generation entry points.

## DT/DA To Excel Via XML

- Title: `DT_CharacterList 表 Xml 配置注意项`
- Token: `[redacted]`
- URL: `[redacted internal wiki URL]`
- Use for: Cases where editor DT/DA data is exported into Excel using XML field definitions.

Important points from the doc:

- Some project data is configured in DT/DA/editor assets, exported to Excel, then generated into binary data for runtime.
- Excel fields are parsed according to XML definitions.
- For nested DA or polymorphic structures, XML defines the export/read shape; update XML when referenced enum/tag/DA structure changes.

## AgentTask Notes

For AgentTask, prefer the local branch source first:

- `X6Game/DesignerConfigurations/CfgDefinitions/aitask.xml` is the source for `aitask.EAITaskType` and related enums.
- `X6Game/DesignerConfigs/CfgDefines/aitask.xml` defines `TaskGroupTypeRule` and `Tb_DT_TaskGroupType` data input.
- `X6Game/Content/Script/Logics/AI/AgentTaskConfig.lua` maps `PaperEnum.Cfg.aitask.EAITaskType.*` to `PaperResource.AITask.*`.
- `X6Game/Content/Script/Config/ResConfig_Version/ResConfig_<version>.lua` may hold branch-version resource keys for new task BPs.
