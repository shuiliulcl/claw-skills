---
name: youtube-briefing
description: Download a YouTube video, polish its auto-generated English subtitles with AI, translate them to Simplified Chinese, and generate a structured Chinese outline. Supports a web UI for queue management and real-time log monitoring. Use this when the user wants to process a YouTube video into Chinese subtitles and a Chinese reading outline.
---

# YouTube Briefing

Processes a YouTube video into three core outputs: a high-quality MP4, AI-polished Chinese subtitle SRT, and a structured Chinese outline in Markdown.

## Core scripts

- `youtube_briefing.py` — CLI entry point. Downloads video and subtitles, runs AI polish + translation, writes all outputs.
- `youtube_briefing_web.py` — Local web UI (port 8765). Wraps the CLI with a job queue, real-time log streaming, and in-browser file access.
- `unreal_video_watch.py` — Scans recent YouTube results for Unreal Engine topics, filters and scores them, optionally hands top picks to `youtube_briefing.py`.

## Setup

1. Install dependencies:

```
pip install -r requirements.txt
```

2. Copy `youtube_briefing.config.json.example` to `youtube_briefing.config.json` and fill in:

```json
{
  "paperhub_api_key": "sk-...",
  "paperhub_api_base": "https://tc-paperhub.diezhi.net/v1/chat/completions",
  "paperhub_model": "glm-5",
  "paperhub_fallback_model": "qwen3.6-plus",
  "ffmpeg_path": "C:\\path\\to\\ffmpeg.exe"
}
```

3. Install `yt-dlp` and optionally `ffmpeg` (for best-quality video merge).

## CLI usage

Process a single video:

```
python youtube_briefing.py https://www.youtube.com/watch?v=...
```

Skip video download (subtitles and outline only):

```
python youtube_briefing.py https://www.youtube.com/watch?v=... --skip-video
```

Disable AI polish and use Google Translate fallback only:

```
python youtube_briefing.py https://www.youtube.com/watch?v=... --no-ai-polish
```

## Web UI

```
python youtube_briefing_web.py
```

Opens `http://127.0.0.1:8765` automatically. Submit a YouTube URL, monitor real-time logs, and access output files directly from the browser. Supports HTTP Range requests so MP4 files can be scrubbed in-browser.

## Unreal Engine video watcher

Scan the last 48 hours of Unreal Engine YouTube content and write a keep/reject report:

```
python unreal_video_watch.py
```

Auto-process the top 2 kept videos:

```
python unreal_video_watch.py --brief-top 2
```

## Outputs (per video)

| File | Description |
|---|---|
| `*.mp4` | Downloaded video (best quality) |
| `subtitles.en.raw.srt` | Original English subtitles |
| `subtitles.zh.ai.srt` | AI-translated Chinese subtitles |
| `transcript.en.txt` | Plain English transcript |
| `transcript.zh.txt` | Plain Chinese transcript |
| `outline.zh.md` | Structured Chinese outline with section summaries |

## AI pipeline

1. Rolling-window auto-subtitle deduplication (collapses yt-dlp sliding-window artifacts)
2. Concurrent AI polish in configurable chunks (default: 35 entries, 3 parallel requests)
3. Per-chunk Google Translate fallback if AI fails — no English passthrough into Chinese SRT
4. AI outline generation: per-section summaries + overall takeaways

## Notes

- `youtube_briefing.config.json` is gitignored — never commit API keys.
- Output directories (`outputs/`, `OutputExample/`) are also gitignored.
- ffmpeg is optional but recommended for best-quality video merging.
