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
