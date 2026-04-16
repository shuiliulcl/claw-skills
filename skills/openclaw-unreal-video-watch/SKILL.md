---
name: openclaw-unreal-video-watch
description: A standalone Windows skill package for OpenClaw that checks the newest videos and stream replays from the official Unreal Engine YouTube channel, filters out Shorts, ads, automotive, architecture, audio, Fortnite and UEFN topics, and writes a keep/reject report. Use this when you want a deployable skill that does not rely on globally installed Python packages or yt-dlp.
---

# OpenClaw Unreal Video Watch

This skill is packaged for standalone deployment on Windows.

## What is bundled

- `scripts/unreal_video_watch.py`: the scanner and filter logic
- `config/watch_config.json`: editable search and filter rules
- `secrets/`: optional local authentication material such as `cookies.txt`
- `install.ps1`: downloads a private portable Python runtime and a private `yt-dlp.exe`
- `run.ps1`: launches the scanner using only bundled runtime/tools
- `register-task.ps1`: creates a Windows scheduled task for tomorrow or a custom time

## Deployment workflow

1. Copy the whole folder to the target machine.
2. Run:

```powershell
powershell -ExecutionPolicy Bypass -File ".\install.ps1"
```

If YouTube blocks anonymous access, add one of these before running:

- Put a Netscape-format cookies file at `%LOCALAPPDATA%\OpenClawUnrealVideoWatch\cookies.txt`
- Or use the package-local fallback at `.\secrets\cookies.txt`
- Or edit `config/watch_config.json` and keep `cookies_from_browser` pointed at a logged-in browser such as `edge`
- See `COOKIES.md` for the full Chrome-oriented setup notes

3. Execute once:

```powershell
powershell -ExecutionPolicy Bypass -File ".\run.ps1"
```

If you already have `.\secrets\cookies.txt` and want to move it into the persistent location:

```powershell
powershell -ExecutionPolicy Bypass -File ".\migrate-cookies.ps1"
```

4. Or register a task for tomorrow:

```powershell
powershell -ExecutionPolicy Bypass -File ".\register-task.ps1"
```

## What it does

1. Reads recent uploads and stream replays from the official `@UnrealEngine` YouTube channel.
2. Rejects low-interest items such as:
   - Shorts and micro-clips
   - Ads and sponsored content
   - Automotive and vehicle demos
   - Architecture and archviz
   - Audio and music centered content
   - Fortnite and UEFN
3. Writes Markdown and JSON reports to `output/`.

## Important notes

- This package avoids relying on globally installed Python packages and `yt-dlp`.
- It still needs network access on first install to download the private runtime and tool binaries.
- For YouTube bot checks, it may still need your own browser cookies or a local `cookies.txt` file.
- The default package is now scoped to the official `@UnrealEngine` channel only.

---

## AI 执行流程（cron / 手动触发时遵循）

### 第一步：运行脚本

```powershell
$src = "C:\Users\banqiang\.openclaw\workspace\scripts\cookies.txt"
$dst = "C:\Users\banqiang\.openclaw\skills\openclaw-unreal-video-watch\secrets\cookies.txt"
Copy-Item $src $dst -Force
powershell -ExecutionPolicy Bypass -File 'C:\Users\banqiang\.openclaw\skills\openclaw-unreal-video-watch\run.ps1'
```

### 第二步：读取报告并验证

找到 `output/` 下最新的 `.json` 报告文件，读取内容。

验证 `generated_at` 字段日期是否为今天：
- 匹配 → 继续
- 不匹配 → 重试一次（重新执行第一步）
- 重试仍不匹配 → 输出 `❌ 报告日期异常，请检查脚本` 并终止，**禁止输出旧数据**

### 第三步：整理报告

从 JSON 中分别提取 videos 频道和 streams 频道的视频，按以下规则输出：

**Videos 频道（`query` 含 `videos`）：**
- 优先：展示所有 `status=keep` 且 `published_at` 在 48h 内的视频
- 如果没有：展示最新一条（不论 status），标注「供确认」
- 如果没有任何 videos 数据：注明「无数据」

**Streams 频道（`query` 含 `streams`）：**
- 优先：展示最近两个 `status=keep` 的视频（按 `published_at` 降序）
- 如果 keep 数量不足两个：用最近的被过滤视频补足，标注「已过滤，供确认」
- 如果没有任何 streams 数据：注明「无数据」

每条视频输出格式：
```
**标题**（发布日期）
一句话中文描述内容。时长 X:XX。
链接
```

规则：
- 标题保留原文，不翻译
- 描述必须用中文重新写，禁止直接抄标题或英文原文
- `published_at=unknown` 时注明「发布日期未知」

### 第四步：输出判断

- 有有效内容（至少 1 条 keep）→ 输出完整报告
- videos 和 streams 均无任何 keep → 输出 `NO_REPLY`
