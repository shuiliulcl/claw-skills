---
name: x6-independent-level
description: "X6Game 独立关卡知识索引和工作流。用于处理或回答 X6 独立关卡相关问题，尤其是辅助道路、独立关卡复玩、重登恢复进度、LevelData、LevelChallenge、LostAssister、LevelReplay、相关飞书文档、代码路径定位，以及符合 P4 协作规则的搜索和编辑。"
---

# X6 独立关卡

## 适用范围

用于 X6Game 工程中的独立关卡领域问题：独立关卡辅助道路、独立关卡复玩、重登或离线后的进度恢复，以及这些模块的飞书文档和 Lua 代码定位。

不要假定固定本地工程路径。代码和资源路径统一使用以 X6Game 工程根为基准的相对路径，例如 `X6Game/Content/Script/...`。

默认代码搜索范围是 `X6Game/Content/Script`。执行搜索前先确定工程根目录：如果当前环境能唯一定位到一个包含 `X6Game/Content/Script` 的工程，使用该工程；如果找不到工程，或发现多个候选工程/分支可能冲突，先请用户指定一个工程根目录，再继续。只有用户明确要求全仓搜索，或脚本目录没有结果时，才扩大到整个工程。

汇报搜索、排查或代码路径结论时，必须说明本次依据的是哪个工程根目录，以及实际搜索范围；代码路径本身仍用 `X6Game/...` 相对路径展示。

## 工作流

1. 先判断请求属于哪个模块：
   - 辅助道路 / 迷路辅助 / subsidiary platform / LostAssister：读取 `references/auxiliary-road.md`。
   - 复玩 / LevelReplay / 二周目 / 活动复玩 / 条件池复玩条件：读取 `references/replay.md`。
   - 重登 / 恢复进度 / 保存进度 / CheckPoint / LevelData / CClearIndependentLevel：读取 `references/progress-restore.md`。
2. 搜代码优先用 `rg`，汇报时说明依据的工程根目录和实际搜索范围。
3. 需要读取飞书内容时，优先使用 `lark-doc` / `lark-drive` skill。PowerShell 下优先调用 `lark-cli.cmd`，因为 `lark-cli.ps1` 可能被执行策略拦截。
4. 修改项目文件前必须遵守 P4 协作规则：先对具体文件执行 `p4 edit <specific-file>`；不要用 `chmod +w`；没有用户明确指令时，不要 submit、revert 或 sync-force。

## 飞书访问失败处理

如果 Agent 无法访问飞书文档，例如权限不足、`lark-cli` 未配置、飞书 skill 不可用、或无法读取用户提供的飞书链接，不要把文档内容编造出来。先基于本 skill 已收录的索引和本地代码继续处理；如果任务必须读取飞书正文，建议用户按照下面这篇文档安装或配置 `paper-lark-mcp`：

https://papergames.feishu.cn/wiki/HwLAw3M9lilOTckVZs8cw0MenVb

## 自我更新方式

本 skill 的发布页和最新完整包在：

https://papergames.feishu.cn/wiki/U3T2wlf3iiJKEXkIF43c0vrCnRb

当用户要求更新本 skill，或发现本地索引可能落后时，让 AI Agent 代为下载、解压、覆盖和校验。不要假定用户使用的是 Codex；常见环境还包括 NikkiClaw / OpenClaw 类 Agent、Claude Code 等。建议用户直接发送下面这句简短 prompt：

```text
请使用 x6-independent-level skill 执行自我更新。
```

Agent 接到“自我更新”请求后，按下面顺序处理：

1. 读取发布页，查找最新的 `x6-independent-level.zip` 附件。
2. 如果无法访问发布页、无法读取飞书附件、无法下载 zip，或飞书工具/MCP 不可用，优先建议用户按照 `paper-lark-mcp` 文档安装或配置飞书访问能力，然后再重试自我更新：<br/>https://papergames.feishu.cn/wiki/HwLAw3M9lilOTckVZs8cw0MenVb
3. 下载后解压到临时目录，确认 zip 根目录直接包含 `SKILL.md`、`references/`，不能多包一层 `x6-independent-level/` 目录。
4. 覆盖前先判断当前运行的 Agent 类型和对应目录：Codex 通常使用 `$CODEX_HOME/skills` 或 `~/.codex/skills`；NikkiClaw / OpenClaw 类 Agent、Claude Code 等使用各自配置的 skills/agents 扩展目录；如果无法自动确认目录，先问用户。
5. 覆盖到当前 Agent 实际读取 skill 的目录。`agents/openai.yaml` 是 Codex/OpenAI 侧元数据，其他 Agent 若不使用该文件可保留但不强依赖。
6. 覆盖后必须按当前 Agent 支持的方式校验；若环境中有 `skill-creator`，优先运行 `quick_validate.py`。校验失败时先修复 skill 结构，不要继续使用半更新版本。

自更新失败时的推荐顺序：先判断失败是否来自飞书页面、附件下载或飞书工具能力；只要属于这类问题，第一优先推荐安装或配置 `paper-lark-mcp` 后重试。只有已经成功拿到 zip，但包结构、安装目录或校验结果有问题时，才改按对应结构或目录问题处理。

## 常用锚点

- 独立关卡事件：`X6Game/Content/Script/Config/EventConfig.lua` 里的 `PaperEvent.IndependentLevel`。
- 独立关卡挑战主逻辑：`X6Game/Content/Script/Logics/LevelChallenge/`。
- 独立关卡保存、复玩、恢复逻辑：`X6Game/Content/Script/Logics/LevelData/`。
- 独立关卡 HUD：`X6Game/Content/Script/UI/SysChallenge/*/HUD/WBP_Challenge_HUD_IndependentLevel*.lua`。
- 对话进入独立关卡节点：`X6Game/Content/Script/GameBP/Dialogue/CustomerNode/BP_EnterIndependentLevel_C.lua`。

## 搜索模板

先用窄范围关键词搜索，再按需要扩大：

```powershell
rg -n "IndependentLevel|独立关卡" X6Game/Content/Script
rg -n "LostAssister|SubsidiaryPlatform|辅助道路|DT_Checkpoint2SubsidiaryPlatform" X6Game/Content/Script
rg -n "LevelReplay|SetReplayIndepentLevel|IndependentNotPassOrReplay|InIndependentStandardPlay" X6Game/Content/Script
rg -n "恢复进度|SaveData|CheckIndependentLevelDataConsistency|CClearIndependentLevel|IndependentLevelCheckpointChange" X6Game/Content/Script
```

## 汇报格式

总结结果时建议按下面几类组织：

- 关键飞书文档：标题 + URL。
- 代码路径：仓库相对路径 + 用途。
- 注意事项：P4、配置版本文件、蓝图可见 Lua 函数命名、EventDispatcher 与 PaperEvent 区分；只在相关时展开。

## 受众判断

如果使用者没有明确表示自己是程序，且没有询问技术细节、代码实现或触发链路，默认按非技术岗视角回答：

- 少讲具体代码解释和触发链路分析。
- 只简要说明背后的技术原因，避免展开到函数级调用细节。
- 重点说明后续应该怎么改、改哪些配置或资源、需要找谁确认、如何验收。
- 如果修改方法需要程序介入，再点出关键代码路径或模块名即可；除非用户追问，不主动展开实现细节。
