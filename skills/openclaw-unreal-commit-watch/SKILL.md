---
name: openclaw-unreal-commit-watch
description: Pull updates for a locally cloned Unreal Engine repository, analyze commits from the last 24 hours, and generate a daily Markdown report with focus sections for Animation, Gameplay, and AI related modules. Use this when OpenClaw needs a recurring Unreal source update digest from a local git repository.
---

# OpenClaw Unreal Commit Watch

监控本地 Unreal Engine 仓库，生成聚焦动画 / Gameplay / AI 模块的每日提交日报。

---

## ⚠️ 输出规则（最高优先级，任何情况下都适用）

- **在最终报告输出之前，绝对不输出任何文字**
- 不输出步骤进度（"正在运行..."、"已读取..."、"开始评估..."等）
- **Evaluator 评分 JSON、分数、分析过程、反馈文字，全部只在内心计算，一字都不得写出来**
- 只有最终报告内容是输出，其他全部静默执行

---

## 执行步骤

**第一步：运行 skill 脚本**
```powershell
powershell -ExecutionPolicy Bypass -File 'C:\Users\banqiang\.openclaw\skills\openclaw-unreal-commit-watch\run.ps1'
```

**第二步：读取最新报告文件**

在 `C:\Users\banqiang\.openclaw\skills\openclaw-unreal-commit-watch\output\` 下找最新的 `.md` 文件（按 `LastWriteTime` 降序取第一个）。

用 `Get-Content -Raw -Encoding UTF8` 读取，确保中文正确显示。

**第三步：质量评估（纯内心判断，不得有任何文字输出）**

在内心按以下四个维度判断报告质量（1-10），全程不写任何字：

| 维度 | 说明 |
|------|------|
| **Coverage** | 是否覆盖 Animation / Gameplay / AI 三个模块？无活跃时是否明确说明？ |
| **Signal-to-noise** | 是否过滤琐碎改动？关键 commit 是否突出影响？ |
| **Actionability** | 是否有影响判断和值得跟踪的点，而不是纯罗列？ |
| **Conciseness** | 长度是否合理（500-2000字）？有无冗余？ |

通过条件：overall ≥ 7.0 且每项 ≥ 6.0

> ⚠️ **评分过程完全在内心完成。JSON、分数、分析文字一字都不得输出。违反即为错误。**
> 唯一允许的输出：报告通过时直接输出报告；不通过时输出评估头 + 报告。没有第三种情况。

**第四步：输出报告**

- **通过** → 直接输出报告内容，无任何前缀后缀
- **不通过** → 按以下精确格式输出（注意空行）：

```
⚠️ 本报告未通过质量评估

评分：Coverage=X, Signal-to-noise=Y, Actionability=Z, Conciseness=W, Overall=V

反馈：<30字以内，逗号分隔核心问题，不换行>

--- 以下为原始报告 ---

<完整报告内容>
```

---

## 报告摘要规则

脚本生成报告后，AI 对摘要内容有以下约束：

### 摘要语言规则

- **摘要必须全中文**，不得中英混排
- commit subject 可保留为英文原文（链接标题），但对应的摘要行必须是纯中文描述
- 错误示例：`ControlRig & 动画 mode: initial release of Direct Mesh Control`
- 正确示例：`ControlRig 动画模式发布 Direct Mesh Control 实验性直接网格体控制插件`

### 低信息量提交处理

以下类型提交不展开摘要，只计入数量：
- 纯注释 / 格式修复
- 文档更新（`.md`、`.txt` 仅改动）
- 版本号 bump、依赖更新
- Revert commit（直接标注"回退"）

### 常见扣分项（供内心判断参考）

- 摘要出现中英混排 → Signal-to-noise 扣分
- AI 模块无内容但未说明原因 → Actionability 扣分
- 影响标注不一致（部分有"建议跟踪"，部分没有）→ Actionability 扣分
- 报告超过 2000 字 → Conciseness 扣分

---

## Cron 触发 Prompt（极简）

cron 只做触发，执行逻辑全在本 SKILL.md 中。

**每日 09:00：**
```
读取并严格执行 C:\Users\banqiang\.openclaw\skills\openclaw-unreal-commit-watch\SKILL.md 中的完整执行流程。
```

---

## 技术说明

### 仓库配置

- 默认仓库路径：`E:\UnrealEngine`
- 分支：`ue5-main`
- 时间窗口：最近 24 小时

### 模块分类

| 模块 | 关键词 / 路径 |
|------|--------------|
| **动画** | Animation、Control Rig、Sequencer、Pose Search、Motion Matching、Retargeting、UAF、IK、SkeletalMesh |
| **Gameplay** | GameplayAbilities、StateTree、Input、Character、Pawn、Mover、CommonUI |
| **AI（辅助开发）** | ECABridge、AIAssistant、NNE、LearningCore、LLM 相关、ToolSet |

> ⚠️ AI 模块指**引擎 AI 辅助开发工具**，不包含游戏内 AI（BehaviorTree、Navigation、Perception、PCG 等）。

### 安全行为

- Fetch 失败 → 硬失败，不生成报告
- 工作树有本地改动 → 跳过 pull，但用 `origin/ue5-main` 分析已 fetch 的内容
- 不执行 reset、rebase 或丢弃本地改动
