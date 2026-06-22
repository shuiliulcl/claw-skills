# Unreal Commit Watch — Report Prompt

本文件定义 AI 构建日报时使用的分类规则、重要度筛选标准和写作规范。
修改此文件即可调整报告风格，无需改动脚本或 SKILL.md。

---

## 模块分类规则

匹配 commit subject 或文件路径（大小写不敏感）：

### 🎬 动画（Animation）
关键词/路径：Animation、Control Rig、Sequencer、Pose Search、Motion Matching、Retarget、UAF、SkeletalMesh、AnimGraph、Montage、IK

> ⚠️ Sequencer、CurveEditor 等属于**动画**模块，不属于 Gameplay。如有歧义，优先按动画归类。

### 🎮 Gameplay
关键词/路径：GameplayAbilities、StateTree、Input、Character、Pawn、Mover、CommonUI、GameFeature、EnhancedInput

### 🤖 AI 引擎工具
关键词/路径：ECABridge、AIAssistant、NNE、LearningCore、LLM

> ⚠️ AI 模块指**引擎 AI 辅助开发工具**，不包含游戏内 AI（BehaviorTree、Navigation、Perception、PCG 等）。

### 其他
不属于以上三类的 commit，统计数量，不展开。

---

## 重要度筛选

**展示**：新增功能、崩溃修复、接口变更、性能优化、内存优化

**跳过（只计入数量，不展开）**：
- cleanup / clean up
- rename / missing file
- warning fix（纯编译警告）
- trivial / backout / back out
- 纯注释/格式修复
- 文档更新（`.md`、`.txt` 仅改动）
- 版本号 bump、依赖更新
- Revert commit（直接标注"回退"，不展开）

---

## 摘要写作规范

### 语言
- **全中文**，专有名词保留英文（Control Rig、Sequencer、StateTree、UAF、Mover、NNE 等）
- **禁止复制或半翻译 commit subject**，必须用自己的理解重写

✅ 正确：`修复多 Actor 骨骼轨道与 Anim Mixer 共存时拖动时间轴导致的崩溃`  
❌ 错误：`修复 崩溃 when scrubbing with Anim Mixer...`

### 影响描述
- 说清楚**哪类开发者**受影响（使用 Control Rig 的 TA、做过场的开发者、Gameplay 程序员等）
- 说清楚**具体影响点**（接口变更需适配、新功能可直接使用、崩溃场景已修复）
- ❌ 禁止写：`高优先级变更，建议跟踪` / `建议关注` / `如您遇到相关场景可升级`

### 每条重点提交格式
```
- **[模块]** 一句话描述做了什么（≤50字）
  - 影响：具体说明哪类开发者受影响、影响点是什么
  - [SHA xxxxxxxx](commit url)
```

---

## 报告整体格式

```
# 虚幻引擎提交日报

**生成时间：** YYYY-MM-DD HH:mm | **提交总数：** N

---

## 今日概览

{分支1} 动画 X 条 · Gameplay Y 条 · AI Z 条
{分支2} 动画 X 条 · Gameplay Y 条 · AI Z 条（若有多分支）

---

## {分支名} — 🎬 动画（X 条）

- **[Control Rig]** ...
  - 影响：...
  - [SHA xxxxxxxx](url)

无高价值提交时写：本时间窗口内无高价值动画提交。

---

## {分支名} — 🎮 Gameplay（Y 条）

（同上格式）

---

## {分支名} — 🤖 AI 引擎工具（Z 条）

无提交时说明：本时间窗口内无 NNE/ECABridge/AIAssistant 相关提交。

---

## 备注

- 分析基准：{分支列表}，最近 24 小时
- 低价值提交已过滤，共 N 条
```

> 多分支时：每个分支独立一组 section（动画/Gameplay/AI），分支名作为 section 前缀。
> 单分支时：section 标题可省略分支前缀，维持原格式。

---

## 质量自查清单（内心完成，不输出）

- [ ] 有无中英混排摘要？
- [ ] 影响描述有无空洞废话？
- [ ] 总长度是否在 500-1500 字以内（多分支可放宽至 2500 字）？
- [ ] 每个分支的每个模块无内容时是否明确说明？
