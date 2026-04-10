---
name: p4-commit-watch
description: 监控 Perforce (P4) 代码仓库的提交活动，支持个人提交半天巡查和组员每日日报两种模式。自动拉取完整提交描述、文件变更列表和代码 diff，并通过 AI 分析改动意图。支持配置多个 stream 仓库，统一监控。

**当以下情况时使用此 Skill**：
(1) 需要设置 p4 提交监控、定时日报
(2) 需要分析某次 p4 提交的改动内容和意图
(3) 需要查看指定用户或组员最近的 p4 提交
(4) 需要配置多仓库（多 stream）的提交巡查
(5) 用户提到"p4 监控"、"提交分析"、"组员日报"、"代码巡查"
---

# P4 Commit Watch

监控 Perforce 提交，生成带 AI diff 分析的报告。

## 目录结构

```
p4-commit-watch/
├── SKILL.md
├── p4-watch-config.json        ← 用户配置文件（从 references/config-example.json 复制后编辑）
├── scripts/
│   ├── p4-self-watch.ps1       ← 个人提交监控（读配置，支持多仓库）
│   └── p4-team-daily.ps1       ← 组员日报（读配置，支持多仓库）
├── references/
│   └── config-example.json     ← 配置文件示例
└── reports/                    ← 自动生成的历史报告
```

## 快速配置

**第一次使用时：**
1. 复制 `references/config-example.json` → `p4-watch-config.json`（skill 根目录）
2. 编辑配置：填写仓库、用户名、组员名单

## 配置文件说明（p4-watch-config.json）

```json
{
  "repos": [                         // 要监控的仓库列表（可多个）
    {
      "name": "Stb_2.5",
      "stream": "//root/game/Stb_2.5/...",
      "label": "稳定版 2.5"          // 报告中显示的名称
    }
  ],
  "self_watch": {
    "p4_user": "shuiliu",            // 个人 p4 用户名
    "hours_back": 12,                // 回溯小时数
    "enabled": true
  },
  "team_watch": {
    "members": ["dashu", "chenglong"],  // 组员 p4 用户名列表
    "hours_back": 24,
    "enabled": true
  },
  "notify": {
    "feishu_open_id": "ou_xxx"       // 飞书通知目标
  }
}
```

## 运行脚本

```powershell
# 个人监控（回溯 12 小时）
powershell -NonInteractive -ExecutionPolicy Bypass -File scripts/p4-self-watch.ps1

# 手动指定回溯时长
powershell -NonInteractive -ExecutionPolicy Bypass -File scripts/p4-self-watch.ps1 -HoursBack 24

# 指定其他配置文件
powershell -NonInteractive -ExecutionPolicy Bypass -File scripts/p4-self-watch.ps1 -ConfigFile D:\my-config.json

# 组员日报
powershell -NonInteractive -ExecutionPolicy Bypass -File scripts/p4-team-daily.ps1
```

## 脚本输出格式

```
[user] P4 Commit Report
Repos: 稳定版 2.5, 开发版 2.8
Period: 04/10 09:00 ~ 04/10 21:00
Total: 2 commit(s)

====================
[稳定版 2.5] CL 680845  2026/04/07 17:27:44
DESC: [X6Game][Script]摆件双人交互流程梳理 | $QPT-90645 | Editor测试通过
TAGS: X6Game, Script
FILES: 5 total (C++/H: 0 | BP: 0 | Lua: 5 | Other: 0)
CHANGED:
  [edit] X6Game/Content/Script/.../BP_Placeable_Mermaid_C.lua
  ...
DIFF_FILE: C:\Users\...\tmpXXXX.txt
```

`DIFF_FILE` 路径指向临时存储的 unified diff 内容，可直接读取做 AI 分析。

## AI 分析工作流

脚本运行后，对每个 `DIFF_FILE`：

1. 用 `read` 工具读取 diff 内容
2. 分析改动意图：重构 / bugfix / 新功能？改了哪些核心逻辑？有无风险点？
3. 用中文写出 2-4 句摘要，格式：
   ```
   [AI分析] 本次提交是...（意图）。主要改动：...。风险点：...（如有）。
   ```
4. 将分析结果附在对应 CL 报告下方，一起发送给用户

## Cron 配置（配置后自动运行）

配置 cron 时使用以下 prompt 模板：

**个人监控（每天 09:00 / 21:00）：**
```
运行 p4 个人提交监控脚本：
powershell -NonInteractive -ExecutionPolicy Bypass -File C:\Users\banqiang\.openclaw\skills\p4-commit-watch\scripts\p4-self-watch.ps1

脚本输出中包含 DIFF_FILE 路径。对每个 DIFF_FILE：
1. 读取 diff 内容
2. 分析改动意图，用中文写 2-4 句摘要
最终将完整报告通过飞书 DM 发送给目标用户。无提交时也发一条通知。
```

**组员日报（每天 22:00）：**
```
运行 p4 组员日报脚本：
powershell -NonInteractive -ExecutionPolicy Bypass -File C:\Users\banqiang\.openclaw\skills\p4-commit-watch\scripts\p4-team-daily.ps1

对每个 DIFF_FILE 读取并用 1-2 句中文摘要改动意图。
将完整报告通过飞书 DM 发送给目标用户。
```

## 已知限制

- Windows 控制台中 p4 中文输出可能乱码，脚本已通过 `p4 describe -s` 绕过（获取完整 UTF-8 描述）
- diff 内容中中文字符串可能仍有乱码（不影响逻辑分析）
- 非代码文件（`.uasset`、`.umap` 等）不生成 diff，只统计数量
- p4 连接配置依赖当前系统的 p4 环境变量（P4PORT / P4USER / P4CLIENT）
