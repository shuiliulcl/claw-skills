---
name: openclaw-unreal-commit-watch
description: Pull updates for a locally cloned Unreal Engine repository, analyze commits from the last 24 hours, and generate a daily Markdown report with focus sections for Animation, Gameplay, and AI related modules. Use this when OpenClaw needs a recurring Unreal source update digest from a local git repository.
---

# OpenClaw Unreal Commit Watch

监控本地 Unreal Engine 仓库,生成聚焦动画 / Gameplay / AI 模块的每日提交日报。

---

## ⚠️ 输出规则(最高优先级,任何情况下都适用)

- **在最终报告输出之前,绝对不输出任何文字**
- 不输出步骤进度("正在运行..."、"已读取..."、"开始评估..."等)
- **Evaluator 评分 JSON、分数、分析过程、反馈文字,全部只在内心计算,一字都不得写出来**
- 只有最终报告内容是输出,其他全部静默执行
- **遇到编码问题（乱码、非 UTF-8 内容）时，静默切换读取方式（如改用 JSON 文件），不输出任何诊断或说明文字**

---

## 执行步骤

**第一步:运行 skill 脚本**
```powershell
powershell -ExecutionPolicy Bypass -File 'C:\Users\banqiang\.openclaw\skills\openclaw-unreal-commit-watch\run.ps1'
```

**第二步:读取最新报告文件，并验证日期**

在 `C:\Users\banqiang\.openclaw\skills\openclaw-unreal-commit-watch\output\` 下找最新的 `.md` 文件。
**排序规则：按文件名中的时间戳（`yyyyMMdd_HHmmss` 格式）降序取第一个，不得用 `LastWriteTime`**（因为文件系统写入时间可能因 gc 等操作晚于报告内容日期，导致取到旧文件）。

用 PowerShell 示例：
```powershell
Get-ChildItem 'C:\Users\banqiang\.openclaw\skills\openclaw-unreal-commit-watch\output\*.md' |
  Sort-Object { if ($_.BaseName -match '(\d{8})_(\d{6})$') { "$($Matches[1])$($Matches[2])" } else { '' } } -Descending |
  Select-Object -First 1
```

用 `Get-Content -Raw -Encoding UTF8` 读取,确保中文正确显示。

**⚠️ 读取后必须验证报告日期（硬检查，不可跳过）：**

- 从报告内容中找到 `生成时间:` 字段，提取其中的日期（格式 `YYYY-MM-DD`）
- 与**当天日期**比较（以本机时区 Asia/Shanghai 为准）
- 如果报告日期 == 今天 → 继续后续步骤
- 如果报告日期 != 今天（旧数据）→ **立即重新执行第一步（最多重试 1 次）**
  - 重试后再读取最新文件，再次验证日期
  - 重试后日期仍不是今天 → **硬失败，输出以下错误并终止**：

```
❌ 日报生成失败：脚本运行后仍未生成今日报告。
报告日期：<实际日期>
预期日期：<今天日期>
请手动检查 run.ps1 是否正常执行。
```

> **禁止在日期验证失败时输出旧数据的报告内容。**

**第三步:质量评估(纯内心判断,不得有任何文字输出)**

在内心按以下四个维度判断报告质量(1-10),全程不写任何字:

| 维度 | 说明 |
|------|------|
| **Coverage** | 是否覆盖 Animation / Gameplay / AI 三个模块?无活跃时是否明确说明? |
| **Signal-to-noise** | 是否过滤琐碎改动?关键 commit 是否突出影响? |
| **Actionability** | 是否有影响判断和值得跟踪的点,而不是纯罗列? |
| **Conciseness** | 长度是否合理(500-2000字)?有无冗余? |

通过条件:overall ≥ 7.0 且每项 ≥ 6.0

> ⚠️ **评分过程完全在内心完成。JSON、分数、分析文字一字都不得输出。违反即为错误。**
> 唯一允许的输出:报告通过时直接输出报告;不通过时输出评估头 + 报告。没有第三种情况。

**第四步：从 JSON 数据构建报告（AI 全程自己写，不使用脚本生成的 md 文本）**

> ⚠️ **不得读取或复用脚本生成的 `.md` 文件内容作为报告正文。** 脚本的摘要是机器词对替换，质量不可靠，必须丢弃。

读取对应的 `.json` 文件（与 md 同名，扩展名不同）：

```powershell
$jsonPath = $reportPath -replace '\.md$', '.json'
$data = Get-Content -Raw -Encoding UTF8 $jsonPath | ConvertFrom-Json
```

JSON 结构为多分支格式：`$data.branches` 是数组，每项有 `branch`、`commits`、`focus`（Animation/Gameplay/AI）、`other`、`skipped` 字段。

```
$data.branches | ForEach-Object {
    $_.branch          # 分支名，如 "ue5-main"
    $_.commits         # 该分支所有 commit
    $_.focus.Animation # 动画相关 commit
    $_.focus.Gameplay  # Gameplay 相关 commit
    $_.focus.AI        # AI 相关 commit
    $_.skipped         # true = 该分支跳过（remote 不存在等）
}
```

拿到数据后，**从头自己构建报告文本**，不复用 md 文件任何内容。
每个分支独立一组 section，参考 `prompts/report_prompt.md` 中的报告格式。

**分类规则（匹配 subject 或文件路径，大小写不敏感）：**
- 动画：Animation、Control Rig、Sequencer、Pose Search、Motion Matching、Retarget、UAF、SkeletalMesh、AnimGraph、Montage
- Gameplay：GameplayAbilities、StateTree、Input、Character、Pawn、Mover、CommonUI
- AI（引擎工具）：ECABridge、AIAssistant、NNE、LearningCore、LLM
- 其他：不属于以上三类

**重要度筛选：** 只展示新增功能、崩溃修复、接口变更、性能优化类提交；跳过 cleanup/rename/warning/missing file/trivial 类。

**每条重点提交格式（全中文，保留必要英文专有名词）：**
```
- **[模块]** 一句话描述做了什么（≤50字）
  - 影响：具体说明哪类开发者受影响、影响点是什么
  - [SHA xxxxxxxx](commit url)
```

**摘要写作硬规则：**
- 全中文，专有名词（Control Rig、Sequencer、StateTree、UAF、Mover 等）保留英文
- 禁止复制或半翻译 commit subject，必须用自己的理解重写
- ❌ 错误：`修复 崩溃 when scrubbing with Anim Mixer...`
- ✅ 正确：`修复多 Actor 骨骼轨道与 Anim Mixer 共存时拖动时间轴导致的崩溃`

**影响描述硬规则：**
- 说清楚哪类开发者受影响（使用 Control Rig 的 TA、做过场的开发者、Gameplay 程序员等）
- 说清楚具体影响点（接口变更需适配、新功能可直接使用、崩溃场景已修复）
- ❌ 禁止写：`高优先级变更，建议跟踪` / `建议关注` / `如您遇到相关场景可升级`

**报告整体格式：**
```
# 虚幻引擎提交日报

**生成时间：** YYYY-MM-DD HH:mm | **提交总数：** N

---

## 今日概览

动画 X 条 · Gameplay Y 条 · AI Z 条

---

## 🎬 动画（X 条）

- **[Control Rig]** ...
  - 影响：...
  - [SHA xxxxxxxx](url)

无高价值提交时写：本时间窗口内无高价值动画提交。

---

## 🎮 Gameplay（Y 条）

（同上格式）

---

## 🤖 AI 引擎工具（Z 条）

无提交时说明：本时间窗口内无 NNE/ECABridge/AIAssistant 相关提交。

---

## 备注

- 分析基准：origin/ue5-main、origin/ue6-main，最近 24 小时
- 低价值提交已过滤，共 N 条
```

**第五步：质量自查（内心完成，不输出任何文字）**

- 有无中英混排摘要？
- 影响描述有无空洞废话？
- 总长度是否在 500-1500 字以内？

不达标就在内心修改，达标后进入第六步。

**第六步：发送报告（飞书 markdown 消息）**

⚠️ **禁止将报告内容内联进 exec 命令字符串**（会导致换行变成字面 `\n`）。

把第四步构建好的报告文本写入临时文件，再读取发送：

```powershell
$tmpPath = [System.IO.Path]::GetTempFileName() + '.md'
[System.IO.File]::WriteAllText($tmpPath, $reportText, [System.Text.Encoding]::UTF8)
$content = Get-Content -Raw -Encoding UTF8 $tmpPath
lark-cli im +messages-send --as bot --user-id ou_2b6334604d63123d4dc232d596e9d46d --markdown $content
Remove-Item $tmpPath -Force
```

发送成功后本步骤完成，不再额外输出文字。

> ⚠️ `**加粗**`、`## 标题` 等 Markdown 语法通过 `--markdown` 会被飞书正确渲染，不要去除星号。

---

## 报告摘要规则

脚本生成报告后,AI 对摘要内容有以下约束:

### 摘要语言规则

- **摘要必须全中文**,不得中英混排
- commit subject 可保留为英文原文(链接标题),但对应的摘要行必须是纯中文描述
- **禁止直接复制粘贴 commit subject 作为摘要**,必须用中文重新解读这个提交做了什么
- 错误示例:`Sequencer: Removes linked filtering CVars and USequencerSettings::bLinkFiltersWithCurveEditor`
- 正确示例:`Sequencer 移除曲线编辑器联动过滤 CVars 及相关设置项,使用时需注意接口变更`

### 低信息量提交处理

以下类型提交不展开摘要,只计入数量:
- 纯注释 / 格式修复
- 文档更新(`.md`、`.txt` 仅改动)
- 版本号 bump、依赖更新
- Revert commit(直接标注"回退")

### 常见扣分项(供内心判断参考)

- 摘要出现中英混排 → Signal-to-noise 扣分
- AI 模块无内容但未说明原因 → Actionability 扣分
- 影响标注不一致（部分有“建议跟踪”，部分没有）→ Actionability 扣分
- 影响描述只写“高优先级变更，建议跟踪”而不说明具体影响对象（哪类开发者、哪个接口）→ Actionability 扣分
- 报告超过 2000 字 → Conciseness 扣分

---

## Cron 触发 Prompt(极简)

cron 只做触发,执行逻辑全在本 SKILL.md 中。

**每日 09:00:**
```
读取并严格执行 C:\Users\banqiang\.openclaw\skills\openclaw-unreal-commit-watch\SKILL.md 中的完整执行流程。
```

---

## 技术说明

### 仓库配置

- 默认仓库路径:`E:\UnrealEngine`
- 分支:`ue5-main`
- 时间窗口:最近 24 小时

### 模块分类

| 模块 | 关键词 / 路径 |
|------|--------------|
| **动画** | Animation、Control Rig、Sequencer、Pose Search、Motion Matching、Retargeting、UAF、IK、SkeletalMesh |
| **Gameplay** | GameplayAbilities、StateTree、Input、Character、Pawn、Mover、CommonUI |
| **AI(辅助开发)** | ECABridge、AIAssistant、NNE、LearningCore、LLM 相关、ToolSet |

> ⚠️ **归类注意**:Sequencer、CurveEditor、FilterMode 等属于**动画**模块,不属于 Gameplay。如有歧义,优先按动画归类。

> ⚠️ AI 模块指**引擎 AI 辅助开发工具**,不包含游戏内 AI(BehaviorTree、Navigation、Perception、PCG 等)。

### 安全行为

- Fetch 失败 → 硬失败,不生成报告
- 工作树有本地改动 → 跳过 pull,但用 `origin/ue5-main` 分析已 fetch 的内容
- 不执行 reset、rebase 或丢弃本地改动
