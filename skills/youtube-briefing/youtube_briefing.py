from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse

try:
    from deep_translator import GoogleTranslator
except ModuleNotFoundError as exc:
    if exc.name == "deep_translator":
        print(
            "Missing dependency: deep_translator\n"
            "Install it with:\n"
            "  py -3 -m pip install -r requirements.txt\n"
            "or:\n"
            "  py -3 -m pip install deep-translator",
            file=sys.stderr,
        )
        raise SystemExit(1)
    raise

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ModuleNotFoundError:
    YouTubeTranscriptApi = None

TIMESTAMP_RE = re.compile(r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})")
INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class SubtitleEntry:
    index: int
    start_ms: int
    end_ms: int
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a YouTube video, polish subtitles, translate to Chinese, and build a Chinese outline."
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--output-dir",
        default=r"D:\YouTubeBriefings",
        help=r"Root output directory. Default: D:\YouTubeBriefings",
    )
    parser.add_argument(
        "--section-minutes",
        type=int,
        default=5,
        help="Minutes per outline section. Default: 5",
    )
    parser.add_argument(
        "--translate-delay",
        type=float,
        default=0.2,
        help="Delay between fallback subtitle translations. Default: 0.2",
    )
    parser.add_argument(
        "--cookies-from-browser",
        default="",
        help="Optional browser name for yt-dlp cookies. Default: disabled",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip video download entirely. Only subtitles and outline will be produced.",
    )
    parser.add_argument(
        "--strict-video",
        action="store_true",
        help="Fail the whole job when video download fails. Default: continue with subtitles and outline.",
    )
    parser.add_argument(
        "--ai-polish",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use AI to polish subtitle content and generate an AI outline. Default: enabled",
    )
    parser.add_argument(
        "--ai-model",
        default=os.environ.get("PAPERHUB_MODEL", "glm-5"),
        help="Model for subtitle polishing and outline generation. Default: glm-5",
    )
    parser.add_argument(
        "--ai-fallback-model",
        default=os.environ.get("PAPERHUB_FALLBACK_MODEL", ""),
        help="Fallback model used when the primary model hits upstream/limit errors. Default: empty",
    )
    parser.add_argument(
        "--ai-chunk-size",
        type=int,
        default=35,
        help="Subtitle items per AI polishing request. Default: 35",
    )
    parser.add_argument(
        "--ai-concurrency",
        type=int,
        default=3,
        help="Concurrent AI subtitle polishing requests. Default: 3",
    )
    parser.add_argument(
        "--ai-endpoint",
        default=os.environ.get("PAPERHUB_API_BASE", "https://tc-paperhub.diezhi.net/v1/chat/completions"),
        help="AI chat completions endpoint",
    )
    return parser.parse_args()


def main() -> int:
    load_local_config()
    args = parse_args()
    total_started = time.perf_counter()
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    metadata_started = time.perf_counter()
    metadata = fetch_metadata(args.url)
    print(f"Metadata fetched in {time.perf_counter() - metadata_started:.1f}s", file=sys.stderr)
    title = metadata.get("title") or "untitled"
    video_id = metadata.get("id") or extract_video_id(args.url) or "unknown"
    job_dir = output_root / f"{safe_name(title)} [{video_id}]"
    job_dir.mkdir(parents=True, exist_ok=True)

    write_json(job_dir / "job.json", {"url": args.url, "metadata": metadata})
    print("Step 1/5: downloading subtitle sources...", file=sys.stderr)
    step_started = time.perf_counter()
    download_subtitles(args.url, job_dir, args.cookies_from_browser)
    print(f"Step 1/5 done in {time.perf_counter() - step_started:.1f}s", file=sys.stderr)
    if args.skip_video:
        print("Step 2/5: video download skipped (--skip-video).", file=sys.stderr)
        video_path = None
    else:
        print("Step 2/5: attempting video download...", file=sys.stderr)
        step_started = time.perf_counter()
        video_path = download_video(
            args.url,
            job_dir,
            args.cookies_from_browser,
            strict=args.strict_video,
        )
        print(f"Step 2/5 done in {time.perf_counter() - step_started:.1f}s", file=sys.stderr)

    step_started = time.perf_counter()
    english_srt = ensure_english_srt(args.url, job_dir)
    raw_entries = parse_srt(english_srt)
    before_collapse = len(raw_entries)
    raw_entries = collapse_rolling_window(raw_entries)
    print(
        f"Step 3/5: loaded {before_collapse} subtitle entries, collapsed to {len(raw_entries)} after rolling-window dedup.",
        file=sys.stderr,
    )
    print(f"Step 3/5 done in {time.perf_counter() - step_started:.1f}s", file=sys.stderr)
    (job_dir / "transcript.en.txt").write_text(build_transcript(raw_entries), encoding="utf-8")

    polished_english_entries = raw_entries
    outline_text: str | None = None

    ai_client = build_ai_client(args.ai_endpoint)
    if args.ai_polish and ai_client is not None:
        try:
            print("Step 4/5: running AI subtitle polishing...", file=sys.stderr)
            step_started = time.perf_counter()
            polished_english_entries, chinese_entries = polish_entries_with_ai(
                client=ai_client,
                model=args.ai_model,
                fallback_model=args.ai_fallback_model,
                entries=raw_entries,
                cache_path=job_dir / "ai-polish-cache.json",
                chunk_size=args.ai_chunk_size,
                concurrency=args.ai_concurrency,
                translate_cache_path=job_dir / "translation-cache.json",
                translate_delay=args.translate_delay,
            )
            print(f"Step 4/5 done in {time.perf_counter() - step_started:.1f}s", file=sys.stderr)
            print("Step 5/5: generating AI outline...", file=sys.stderr)
            step_started = time.perf_counter()
            outline_text = build_ai_outline_markdown(
                client=ai_client,
                model=args.ai_model,
                fallback_model=args.ai_fallback_model,
                title=title,
                url=args.url,
                translated_entries=chinese_entries,
                section_minutes=args.section_minutes,
                cache_path=job_dir / "ai-outline-cache.json",
            )
            print(f"Step 5/5 done in {time.perf_counter() - step_started:.1f}s", file=sys.stderr)
        except Exception as exc:
            print(
                f"AI polishing failed; falling back to basic translation. Error: {exc}",
                file=sys.stderr,
            )
            step_started = time.perf_counter()
            chinese_entries = translate_entries(
                entries=raw_entries,
                cache_path=job_dir / "translation-cache.json",
                delay_seconds=args.translate_delay,
            )
            print(f"Fallback translation done in {time.perf_counter() - step_started:.1f}s", file=sys.stderr)
    else:
        if args.ai_polish:
            print(
                "AI polishing is enabled but PAPERHUB_API_KEY is missing. Falling back to basic translation.",
                file=sys.stderr,
            )
        print("Step 4/5: running fallback translation...", file=sys.stderr)
        step_started = time.perf_counter()
        chinese_entries = translate_entries(
            entries=raw_entries,
            cache_path=job_dir / "translation-cache.json",
            delay_seconds=args.translate_delay,
        )
        print(f"Step 4/5 done in {time.perf_counter() - step_started:.1f}s", file=sys.stderr)

    canonical_english_srt = job_dir / "subtitles.en.raw.srt"
    write_srt(canonical_english_srt, raw_entries)
    (job_dir / "transcript.en.cleaned.txt").write_text(
        build_transcript(polished_english_entries),
        encoding="utf-8",
    )

    chinese_srt = build_variant_srt_path(english_srt, ".zh.")
    write_srt(chinese_srt, chinese_entries)
    canonical_chinese_srt = job_dir / "subtitles.zh.ai.srt"
    write_srt(canonical_chinese_srt, chinese_entries)
    (job_dir / "transcript.zh.txt").write_text(build_transcript(chinese_entries), encoding="utf-8")

    final_outline = outline_text or build_outline_markdown(
        title=title,
        url=args.url,
        translated_entries=chinese_entries,
        section_minutes=args.section_minutes,
    )
    (job_dir / "outline.zh.md").write_text(final_outline, encoding="utf-8")

    print("Done")
    print(f"Job directory: {job_dir}")
    if video_path is not None:
        print(f"Video: {video_path.name}")
    else:
        print("Video: skipped or failed to download")
    print(f"English subtitles: {english_srt.name}")
    print(f"Chinese subtitles: {chinese_srt.name}")
    print(f"Canonical English subtitles: {canonical_english_srt.name}")
    print(f"Canonical AI Chinese subtitles: {canonical_chinese_srt.name}")
    print("Outline: outline.zh.md")
    print(f"Total time: {time.perf_counter() - total_started:.1f}s", file=sys.stderr)
    return 0


def load_local_config() -> None:
    config_path = Path(__file__).with_name("youtube_briefing.config.json")
    if not config_path.exists():
        return
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read local config file: {exc}", file=sys.stderr)
        return

    env_mapping = {
        "paperhub_api_key": "PAPERHUB_API_KEY",
        "paperhub_api_base": "PAPERHUB_API_BASE",
        "paperhub_model": "PAPERHUB_MODEL",
        "paperhub_fallback_model": "PAPERHUB_FALLBACK_MODEL",
        "ffmpeg_path": "FFMPEG_PATH",
    }
    for key, env_name in env_mapping.items():
        value = payload.get(key)
        if value and not os.environ.get(env_name):
            os.environ[env_name] = str(value)


def build_ai_client(endpoint: str) -> dict | None:
    api_key = os.environ.get("PAPERHUB_API_KEY")
    if not api_key:
        return None
    return {"endpoint": endpoint, "api_key": api_key}


def fetch_metadata(url: str) -> dict:
    result = run_command(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-single-json",
            "--no-warnings",
            "--no-check-certificates",
            url,
        ]
    )
    return json.loads(result.stdout)


def download_subtitles(url: str, job_dir: Path, cookies_from_browser: str | None) -> None:
    template = str(job_dir / "%(title).120B [%(id)s].%(ext)s")
    base_command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-check-certificates",
        "--skip-download",
        "--write-sub",
        "--write-auto-sub",
        "--sub-langs",
        "en.*",
        "--output",
        template,
    ]
    run_yt_dlp_with_cookie_fallback(base_command, url, cookies_from_browser)


def download_video(
    url: str,
    job_dir: Path,
    cookies_from_browser: str | None,
    strict: bool,
) -> Path | None:
    template = str(job_dir / "%(title).120B [%(id)s].%(ext)s")
    ffmpeg_path = resolve_ffmpeg_path()
    ffmpeg_available = ffmpeg_path is not None
    format_selector = (
        "bestvideo*+bestaudio/best"
        if ffmpeg_available
        else "best[ext=mp4]/mp4/best"
    )
    base_command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-check-certificates",
        "--force-overwrites",
        "-f",
        format_selector,
        "--output",
        template,
    ]
    if ffmpeg_available:
        print(f"Using ffmpeg for high-quality merge: {ffmpeg_path}", file=sys.stderr)
        base_command.extend(["--ffmpeg-location", ffmpeg_path])
        base_command.extend(["--merge-output-format", "mp4"])

    try:
        run_yt_dlp_with_cookie_fallback(base_command, url, cookies_from_browser)
    except RuntimeError as exc:
        if strict:
            raise
        print(
            "\n".join(
                [
                    "Warning: video download failed, but subtitle pipeline will continue.",
                    "Common fixes:",
                    "  1. Upgrade yt-dlp: py -3 -m pip install -U yt-dlp",
                    "  2. Install ffmpeg to enable bestvideo+bestaudio merging for higher quality",
                    "  3. Upgrade Python to 3.10+ for yt-dlp if possible",
                    "  4. Use PAPERHUB_API_KEY + AI polishing so the subtitles are cleaner even without the video file",
                    "",
                    "Original error:",
                    str(exc),
                ]
            ),
            file=sys.stderr,
        )
        return None
    return find_downloaded_video(job_dir)


def has_ffmpeg() -> bool:
    return resolve_ffmpeg_path() is not None


def resolve_ffmpeg_path() -> str | None:
    configured = os.environ.get("FFMPEG_PATH", "").strip()
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("ffmpeg")
    return discovered


def ensure_english_srt(url: str, job_dir: Path) -> Path:
    try:
        return find_english_srt(job_dir)
    except FileNotFoundError:
        vtt_path = find_english_vtt(job_dir)
        if vtt_path is not None:
            print("No English SRT found; converting downloaded VTT subtitles locally.", file=sys.stderr)
            entries = parse_vtt(vtt_path)
            srt_path = vtt_path.with_suffix(".srt")
            write_srt(srt_path, entries)
            return srt_path
        print("No English subtitles from yt-dlp; trying youtube-transcript-api fallback.", file=sys.stderr)
        return fetch_transcript_fallback(url, job_dir)


def find_english_srt(job_dir: Path) -> Path:
    candidates = sorted(job_dir.glob("*.en*.srt"))
    if not candidates:
        raise FileNotFoundError("No English subtitle file was found.")
    human_preferred = [path for path in candidates if ".en-orig." in path.name or ".en." in path.name]
    return human_preferred[0] if human_preferred else candidates[0]


def find_english_vtt(job_dir: Path) -> Path | None:
    candidates = sorted(job_dir.glob("*.en*.vtt"))
    if not candidates:
        return None
    human_preferred = [path for path in candidates if ".en-orig." in path.name or ".en." in path.name]
    return human_preferred[0] if human_preferred else candidates[0]


def fetch_transcript_fallback(url: str, job_dir: Path) -> Path:
    if YouTubeTranscriptApi is None:
        raise FileNotFoundError(
            "No English subtitle file was found, and youtube-transcript-api is not installed. "
            "Install it with: py -3 -m pip install youtube-transcript-api"
        )
    video_id = extract_video_id(url)
    if not video_id:
        raise FileNotFoundError("No English subtitle file was found, and the YouTube video ID could not be parsed.")

    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(video_id, languages=["en"])
    except TypeError:
        transcript_list = api.list(video_id)
        transcript = transcript_list.find_transcript(["en"]).fetch()

    entries: list[SubtitleEntry] = []
    for index, item in enumerate(transcript, start=1):
        text = cleanup_subtitle_text(unescape(item["text"] if isinstance(item, dict) else item.text))
        if not text:
            continue
        start_seconds = item["start"] if isinstance(item, dict) else item.start
        duration_seconds = item["duration"] if isinstance(item, dict) else item.duration
        start_ms = int(float(start_seconds) * 1000)
        end_ms = int((float(start_seconds) + float(duration_seconds)) * 1000)
        entries.append(SubtitleEntry(index=index, start_ms=start_ms, end_ms=end_ms, text=text))

    entries = dedupe_entries(entries)
    if not entries:
        raise FileNotFoundError("Transcript fallback returned no usable English entries.")

    srt_path = job_dir / "fallback.en.srt"
    write_srt(srt_path, entries)
    return srt_path


def run_yt_dlp_with_cookie_fallback(
    base_command: list[str],
    url: str,
    preferred_browser: str | None,
) -> None:
    last_error: RuntimeError | None = None
    for browser in build_cookie_fallback_order(preferred_browser):
        command = list(base_command)
        if browser:
            command.extend(["--cookies-from-browser", browser])
            print(f"Trying yt-dlp with browser cookies: {browser}", file=sys.stderr)
        else:
            print("Trying yt-dlp without browser cookies", file=sys.stderr)
        command.append(url)
        try:
            run_command(command)
            return
        except RuntimeError as exc:
            last_error = exc
            message = str(exc)
            if browser and is_cookie_decrypt_error(message):
                print(f"Cookie extraction failed for {browser}; falling back to another mode.", file=sys.stderr)
                continue
            if browser and is_cookie_permission_error(message):
                print(f"Cookie database seems locked for {browser}; close the browser and retry if needed.", file=sys.stderr)
                continue
            if browser and is_cookie_copy_error(message):
                print(f"Could not copy cookie database for {browser}; trying the next fallback.", file=sys.stderr)
                continue
            if browser and is_youtube_403_error(message):
                print("Cookie-backed mode still hit YouTube restrictions; trying the next fallback.", file=sys.stderr)
                continue
            if browser is None:
                break
            raise
    if last_error is not None:
        raise last_error


def build_cookie_fallback_order(preferred_browser: str | None) -> list[str | None]:
    ordered: list[str | None] = []
    normalized = preferred_browser.strip() if preferred_browser else None
    for item in [normalized, None]:
        if item not in ordered:
            ordered.append(item)
    return ordered


def find_downloaded_video(job_dir: Path) -> Path | None:
    candidates: list[Path] = []
    for pattern in ("*.mp4", "*.mkv", "*.webm", "*.mov"):
        candidates.extend(job_dir.glob(pattern))
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def parse_srt(path: Path) -> list[SubtitleEntry]:
    raw_text = path.read_text(encoding="utf-8-sig")
    raw_blocks = raw_text.strip().split("\n\n")
    entries: list[SubtitleEntry] = []
    for block in raw_blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0])
        except ValueError:
            continue
        if " --> " not in lines[1]:
            continue
        start_text, end_text = lines[1].split(" --> ", 1)
        text = cleanup_subtitle_text(" ".join(lines[2:]))
        if not text:
            continue
        entries.append(
            SubtitleEntry(
                index=index,
                start_ms=parse_timestamp_to_ms(start_text),
                end_ms=parse_timestamp_to_ms(end_text),
                text=text,
            )
        )
    return dedupe_entries(entries)


def parse_vtt(path: Path) -> list[SubtitleEntry]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    entries: list[SubtitleEntry] = []
    index = 1
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "WEBVTT" or line.startswith("Kind:") or line.startswith("Language:"):
            i += 1
            continue
        if "-->" not in line:
            i += 1
            continue

        start_text, end_text = [part.strip().split(" ")[0] for part in line.split("-->", 1)]
        text_lines: list[str] = []
        i += 1
        while i < len(lines) and lines[i].strip():
            current = lines[i].strip()
            if current.startswith("NOTE") or current.startswith("STYLE"):
                break
            text_lines.append(current)
            i += 1

        text = cleanup_subtitle_text(" ".join(text_lines))
        if text:
            entries.append(
                SubtitleEntry(
                    index=index,
                    start_ms=parse_vtt_timestamp_to_ms(start_text),
                    end_ms=parse_vtt_timestamp_to_ms(end_text),
                    text=text,
                )
            )
            index += 1
        i += 1
    return dedupe_entries(entries)


def build_transcript(entries: Iterable[SubtitleEntry]) -> str:
    lines: list[str] = []
    previous = ""
    for entry in entries:
        if entry.text != previous:
            lines.append(entry.text)
        previous = entry.text
    return "\n".join(lines)


def polish_entries_with_ai(
    client: dict,
    model: str,
    fallback_model: str,
    entries: list[SubtitleEntry],
    cache_path: Path,
    chunk_size: int,
    concurrency: int,
    translate_cache_path: Path | None = None,
    translate_delay: float = 0.2,
) -> tuple[list[SubtitleEntry], list[SubtitleEntry]]:
    cache = load_cache(cache_path)
    chunks = chunk_entries(entries, max(chunk_size, 5))
    polished_en_by_index: dict[int, SubtitleEntry] = {}
    polished_zh_by_index: dict[int, SubtitleEntry] = {}
    cache_hits = 0
    remote_requests = 0

    cached_chunk_results: dict[int, dict] = {}
    pending_chunks: list[tuple[int, list[SubtitleEntry], str]] = []

    for chunk_index, chunk in enumerate(chunks, start=1):
        cache_key = compute_ai_chunk_key(chunk, model, "polish-v1")
        data = cache.get(cache_key)
        if data is not None:
            cache_hits += 1
            print(
                f"AI polishing chunk {chunk_index}/{len(chunks)} cache hit ({len(chunk)} subtitle items)",
                file=sys.stderr,
            )
            cached_chunk_results[chunk_index] = data
        else:
            pending_chunks.append((chunk_index, chunk, cache_key))

    if pending_chunks:
        max_workers = max(1, min(concurrency, len(pending_chunks)))
        print(
            f"AI polishing remote requests: {len(pending_chunks)} chunks with concurrency {max_workers}",
            file=sys.stderr,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(request_polish_chunk, client, model, fallback_model, chunk_index, len(chunks), chunk): (chunk_index, chunk, cache_key)
                for chunk_index, chunk, cache_key in pending_chunks
            }
            for future in concurrent.futures.as_completed(future_map):
                chunk_index, chunk, cache_key = future_map[future]
                data = future.result()
                remote_requests += 1
                cached_chunk_results[chunk_index] = data
                if not data.get("_fallback"):
                    cache[cache_key] = data
                    write_json(cache_path, cache)

    # Collect entries from fallback chunks so we can Google-translate them.
    fallback_entries: list[SubtitleEntry] = []
    for chunk_index, chunk in enumerate(chunks, start=1):
        if cached_chunk_results[chunk_index].get("_fallback"):
            fallback_entries.extend(chunk)

    google_zh_by_index: dict[int, str] = {}
    if fallback_entries:
        print(
            f"AI polishing: {len(fallback_entries)} entries from failed chunks, translating with Google Translate...",
            file=sys.stderr,
        )
        gt_cache_path = translate_cache_path or cache_path.with_name(cache_path.stem + "-gt-fallback.json")
        google_translated = translate_entries(
            entries=fallback_entries,
            cache_path=gt_cache_path,
            delay_seconds=translate_delay,
        )
        google_zh_by_index = {e.index: e.text for e in google_translated}

    for chunk_index, chunk in enumerate(chunks, start=1):
        data = cached_chunk_results[chunk_index]
        items = data.get("items", [])
        normalized = {int(item["index"]): item for item in items if "index" in item}
        for entry in chunk:
            item = normalized.get(entry.index, {})
            corrected_en = cleanup_subtitle_text(str(item.get("corrected_en") or entry.text))
            # Use Google Translate result for fallback chunks; otherwise use AI result.
            if data.get("_fallback") and entry.index in google_zh_by_index:
                translated_zh = google_zh_by_index[entry.index]
            else:
                translated_zh = cleanup_subtitle_text(str(item.get("translated_zh") or corrected_en or entry.text))
            polished_en_by_index[entry.index] = SubtitleEntry(
                index=entry.index,
                start_ms=entry.start_ms,
                end_ms=entry.end_ms,
                text=corrected_en or entry.text,
            )
            polished_zh_by_index[entry.index] = SubtitleEntry(
                index=entry.index,
                start_ms=entry.start_ms,
                end_ms=entry.end_ms,
                text=translated_zh or corrected_en or entry.text,
            )

    polished_en = [polished_en_by_index[entry.index] for entry in entries if entry.index in polished_en_by_index]
    polished_zh = [polished_zh_by_index[entry.index] for entry in entries if entry.index in polished_zh_by_index]
    print(
        f"AI polishing summary: {cache_hits} cache hits, {remote_requests} remote requests, "
        f"{len(chunks)} total chunks, {len(fallback_entries)} entries fell back to Google Translate",
        file=sys.stderr,
    )
    return polished_en, polished_zh


def request_polish_chunk(
    client: dict,
    model: str,
    fallback_model: str,
    chunk_index: int,
    total_chunks: int,
    chunk: list[SubtitleEntry],
) -> dict:
    chunk_started = time.perf_counter()
    print(
        f"AI polishing chunk {chunk_index}/{total_chunks} remote request ({len(chunk)} subtitle items)...",
        file=sys.stderr,
    )
    payload = [
        {
            "index": entry.index,
            "start": format_ms(entry.start_ms),
            "end": format_ms(entry.end_ms),
            "text": entry.text,
        }
        for entry in chunk
    ]
    try:
        data = request_json_with_retry(
            client=client,
            model=model,
            fallback_model=fallback_model,
            system_prompt=(
                "You repair noisy English subtitles and create natural Simplified Chinese translations. "
                "Return strict JSON only."
            ),
            user_prompt=build_subtitle_polish_prompt(payload),
        )
        print(
            f"AI polishing chunk {chunk_index}/{total_chunks} done in {time.perf_counter() - chunk_started:.1f}s",
            file=sys.stderr,
        )
        return data
    except Exception as exc:
        print(
            f"AI polishing chunk {chunk_index}/{total_chunks} failed after {time.perf_counter() - chunk_started:.1f}s; using original text. Error: {exc}",
            file=sys.stderr,
        )
        return {
            "_fallback": True,
            "items": [
                {
                    "index": entry.index,
                    "corrected_en": entry.text,
                    "translated_zh": entry.text,
                }
                for entry in chunk
            ],
        }


def build_subtitle_polish_prompt(payload: list[dict[str, str]]) -> str:
    return (
        "You will receive noisy auto-generated English subtitle items.\n"
        "Task:\n"
        "1. Correct obvious ASR errors when the intended meaning is clear.\n"
        "2. Improve readability while keeping the original meaning.\n"
        "3. Keep one output item per input item.\n"
        "4. Produce natural Simplified Chinese suitable for quick reading.\n"
        "5. Keep technical terms consistent.\n"
        "6. Do not invent facts.\n\n"
        "Return JSON exactly like:\n"
        "{\"items\":[{\"index\":1,\"corrected_en\":\"...\",\"translated_zh\":\"...\"}]}\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def build_ai_outline_markdown(
    client: dict,
    model: str,
    fallback_model: str,
    title: str,
    url: str,
    translated_entries: list[SubtitleEntry],
    section_minutes: int,
    cache_path: Path,
) -> str:
    cache = load_cache(cache_path)
    sections = split_entries_by_time(translated_entries, section_minutes)
    section_summaries: list[dict[str, object]] = []

    for section_index, section in enumerate(sections, start=1):
        section_started = time.perf_counter()
        print(f"AI outline section {section_index}/{len(sections)}...", file=sys.stderr)
        payload = {
            "start": format_mmss(section[0].start_ms),
            "end": format_mmss(section[-1].end_ms),
            "transcript_zh": build_transcript(section),
        }
        cache_key = compute_ai_text_key(json.dumps(payload, ensure_ascii=False), model, "outline-section-v1")
        summary = cache.get(cache_key)
        if summary is None:
            summary = request_json_with_retry(
                client=client,
                model=model,
                fallback_model=fallback_model,
                system_prompt="You summarize transcript sections into concise Chinese notes. Return strict JSON only.",
                user_prompt=(
                    "Summarize this section into one short Chinese title and 2-4 Chinese bullets.\n"
                    "Return JSON exactly like:\n"
                    "{\"title\":\"...\",\"bullets\":[\"...\",\"...\"]}\n\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            )
            cache[cache_key] = summary
            write_json(cache_path, cache)
        print(
            f"AI outline section {section_index}/{len(sections)} done in {time.perf_counter() - section_started:.1f}s",
            file=sys.stderr,
        )
        section_summaries.append(
            {
                "start": payload["start"],
                "end": payload["end"],
                "title": str(summary.get("title") or f"{payload['start']} - {payload['end']}"),
                "bullets": [str(item) for item in summary.get("bullets", []) if str(item).strip()],
            }
        )

    overview_payload = {"sections": section_summaries}
    overview_key = compute_ai_text_key(json.dumps(overview_payload, ensure_ascii=False), model, "outline-overview-v1")
    overview = cache.get(overview_key)
    if overview is None:
        print("AI outline overview...", file=sys.stderr)
        overview_started = time.perf_counter()
        overview = request_json_with_retry(
            client=client,
            model=model,
            fallback_model=fallback_model,
            system_prompt="You write short Chinese briefing overviews. Return strict JSON only.",
            user_prompt=(
                "Based on these section summaries, write a compact Chinese overview.\n"
                "Return JSON exactly like:\n"
                "{\"takeaways\":[\"...\",\"...\",\"...\"],\"audience\":\"...\"}\n\n"
                f"{json.dumps(overview_payload, ensure_ascii=False)}"
            ),
        )
        cache[overview_key] = overview
        write_json(cache_path, cache)
        print(f"AI outline overview done in {time.perf_counter() - overview_started:.1f}s", file=sys.stderr)

    lines = [
        f"# {title}",
        "",
        f"- 来源：{url}",
        "- 生成方式：AI 字幕修正 + 中文字幕润色 + AI 中文大纲",
        "",
        "## 快速结论",
        "",
    ]
    takeaways = [str(item).strip() for item in overview.get("takeaways", []) if str(item).strip()]
    if takeaways:
        for item in takeaways[:5]:
            lines.append(f"- {item}")
    else:
        lines.append("- 这一视频的核心内容请结合下方分段速读查看。")

    audience = str(overview.get("audience") or "").strip()
    if audience:
        lines.extend(["", f"适合谁看：{audience}"])

    lines.extend(["", "## 分段速读", ""])
    for section in section_summaries:
        lines.append(f"### {section['start']} - {section['end']} | {section['title']}")
        lines.append("")
        bullets = section.get("bullets", [])
        if bullets:
            for bullet in bullets:
                lines.append(f"- {bullet}")
        else:
            lines.append("- 这一段以过渡说明为主，可结合中文字幕查看。")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def translate_entries(
    entries: list[SubtitleEntry],
    cache_path: Path,
    delay_seconds: float,
) -> list[SubtitleEntry]:
    cache = load_cache(cache_path)
    translator = GoogleTranslator(source="en", target="zh-CN")
    translated: list[SubtitleEntry] = []
    ssl_warning_shown = False
    translator_available = True

    for entry in entries:
        source_text = entry.text
        if source_text in cache:
            zh_text = cache[source_text]
        else:
            if translator_available:
                zh_text, translator_available, show_ssl_warning = translate_text_with_fallback(
                    translator,
                    source_text,
                )
                if show_ssl_warning and not ssl_warning_shown:
                    print(
                        "Fallback Google translation hit an SSL certificate issue; remaining untranslated lines will keep the original text.",
                        file=sys.stderr,
                    )
                    ssl_warning_shown = True
            else:
                zh_text = source_text
            cache[source_text] = zh_text
            write_json(cache_path, cache)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
        translated.append(
            SubtitleEntry(
                index=entry.index,
                start_ms=entry.start_ms,
                end_ms=entry.end_ms,
                text=cleanup_subtitle_text(zh_text),
            )
        )
    return translated


def translate_text_with_fallback(
    translator: GoogleTranslator,
    source_text: str,
) -> tuple[str, bool, bool]:
    try:
        result = translator.translate(source_text)
        if result:
            return result, True, False
    except Exception as exc:
        if is_ssl_certificate_error(exc):
            return source_text, False, True
        print(f"Translation failed for one subtitle entry; keeping original text. Error: {exc}", file=sys.stderr)

    parts = split_for_translation(source_text)
    if len(parts) > 1:
        translated_parts: list[str] = []
        for part in parts:
            try:
                translated_parts.append(translator.translate(part) or part)
            except Exception as exc:
                if is_ssl_certificate_error(exc):
                    return source_text, False, True
                translated_parts.append(part)
            except Exception:
                translated_parts.append(part)
        merged = " ".join(item.strip() for item in translated_parts if item.strip()).strip()
        if merged:
            return merged, True, False
    return source_text, True, False


def split_for_translation(text: str) -> list[str]:
    parts = re.split(r"(?<=[,;:.!?])\s+|\s+-->\s+|\s+-\s+", text)
    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned if cleaned else [text]


def split_entries_by_time(entries: list[SubtitleEntry], section_minutes: int) -> list[list[SubtitleEntry]]:
    section_ms = max(section_minutes, 1) * 60 * 1000
    sections: list[list[SubtitleEntry]] = []
    current: list[SubtitleEntry] = []
    current_start = 0
    for entry in entries:
        if not current:
            current = [entry]
            current_start = entry.start_ms
            continue
        if entry.start_ms - current_start < section_ms:
            current.append(entry)
            continue
        sections.append(current)
        current = [entry]
        current_start = entry.start_ms
    if current:
        sections.append(current)
    return sections


def chunk_entries(entries: list[SubtitleEntry], chunk_size: int) -> list[list[SubtitleEntry]]:
    return [entries[i:i + chunk_size] for i in range(0, len(entries), chunk_size)]


def write_srt(path: Path, entries: Iterable[SubtitleEntry]) -> None:
    blocks: list[str] = []
    for i, entry in enumerate(entries, start=1):
        blocks.append(
            "\n".join(
                [
                    str(i),
                    f"{format_ms(entry.start_ms)} --> {format_ms(entry.end_ms)}",
                    entry.text,
                ]
            )
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def build_outline_markdown(
    title: str,
    url: str,
    translated_entries: list[SubtitleEntry],
    section_minutes: int,
) -> str:
    sections = split_entries_by_time(translated_entries, section_minutes)
    lines = [
        f"# {title}",
        "",
        f"- 来源：{url}",
        "- 生成方式：基础翻译 + 规则化中文大纲",
        "",
        "## 快速结论",
        "",
    ]
    for point in collect_outline_points(translated_entries, limit=5):
        lines.append(f"- {point}")

    lines.extend(["", "## 分段速读", ""])
    for section in sections:
        start_label = format_mmss(section[0].start_ms)
        end_label = format_mmss(section[-1].end_ms)
        lines.append(f"### {start_label} - {end_label}")
        lines.append("")
        for point in collect_outline_points(section, limit=3):
            lines.append(f"- {point}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def collect_outline_points(entries: list[SubtitleEntry], limit: int) -> list[str]:
    points: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        text = entry.text.strip()
        if len(text) < 8 or text in seen:
            continue
        seen.add(text)
        points.append(text)
        if len(points) >= limit:
            break
    if not points:
        points.append("这一段以口语过渡为主，建议直接查看中文字幕文件。")
    return points


def dedupe_entries(entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
    deduped: list[SubtitleEntry] = []
    previous_text = None
    for entry in entries:
        if entry.text == previous_text:
            continue
        deduped.append(entry)
        previous_text = entry.text
    return deduped


def collapse_rolling_window(entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
    """
    yt-dlp auto-subtitles use a rolling window format: each entry shows the tail
    of the previous sentence plus new words, and 10ms transition frames show only
    the old tail.  Example:
        entry N   (10ms): "welcome to Inside"
        entry N+1 (3s):   "welcome to Inside Unreal, a show where we learn"
        entry N+2 (10ms): "Unreal, a show where we learn"
        entry N+3 (3s):   "Unreal, a show where we learn and celebrate..."

    This function:
    1. Drops transition frames (duration < 100ms).
    2. For each remaining entry, strips the overlapping prefix that was already
       present in the previous entry, keeping only the newly spoken words.
    3. Re-indexes the result.

    Only collapses when the overlap is >= 3 words to avoid stripping content
    from normal (non-rolling-window) subtitles.
    """
    MIN_DURATION_MS = 100
    MIN_OVERLAP = 3

    filtered = [e for e in entries if (e.end_ms - e.start_ms) >= MIN_DURATION_MS]
    if not filtered:
        return entries

    result: list[SubtitleEntry] = []
    prev_words: list[str] = []

    for entry in filtered:
        words = entry.text.split()
        # Find the longest suffix of prev_words that is a prefix of current words.
        overlap = 0
        limit = min(len(prev_words), len(words) - 1)  # keep at least 1 word
        for length in range(limit, MIN_OVERLAP - 1, -1):
            if prev_words[-length:] == words[:length]:
                overlap = length
                break

        new_words = words[overlap:]
        result.append(SubtitleEntry(
            index=entry.index,
            start_ms=entry.start_ms,
            end_ms=entry.end_ms,
            text=" ".join(new_words) if new_words else entry.text,
        ))
        prev_words = words  # always compare against the full original text

    for i, e in enumerate(result, start=1):
        e.index = i

    return result


def cleanup_subtitle_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\([Mm]usic\)", " ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def build_variant_srt_path(english_srt: Path, marker: str) -> Path:
    name = english_srt.name
    if ".en." in name:
        return english_srt.with_name(name.replace(".en.", marker))
    if ".en-" in name:
        replacement = marker[:-1] + "-" if marker.endswith(".") else marker + "-"
        return english_srt.with_name(name.replace(".en-", replacement))
    return english_srt.with_name(f"{english_srt.stem}{marker[:-1]}{english_srt.suffix}")


def parse_timestamp_to_ms(value: str) -> int:
    match = TIMESTAMP_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    h = int(match.group("h"))
    m = int(match.group("m"))
    s = int(match.group("s"))
    ms = int(match.group("ms"))
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def parse_vtt_timestamp_to_ms(value: str) -> int:
    cleaned = value.strip().replace(".", ",")
    if cleaned.count(":") == 1:
        cleaned = f"00:{cleaned}"
    return parse_timestamp_to_ms(cleaned)


def format_ms(value: int) -> str:
    hours, rem = divmod(value, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def format_mmss(value: int) -> str:
    total_seconds = value // 1000
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def safe_name(value: str) -> str:
    cleaned = INVALID_FS_CHARS.sub("_", value)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip().rstrip(".")
    return cleaned[:120] or "untitled"


def compute_ai_chunk_key(entries: list[SubtitleEntry], model: str, version: str) -> str:
    raw = json.dumps(
        [{"i": e.index, "s": e.start_ms, "e": e.end_ms, "t": e.text} for e in entries],
        ensure_ascii=False,
    )
    return compute_ai_text_key(raw, model, version)


def compute_ai_text_key(text: str, model: str, version: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{version}:{model}:{digest}"


def run_openai_text(
    client: dict,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    request = urllib.request.Request(
        client["endpoint"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {client['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI endpoint returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI endpoint request failed: {exc}") from exc

    data = json.loads(body)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"AI response did not contain choices: {body[:300]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    raise RuntimeError(f"AI response did not contain message content: {body[:300]}")


def request_json_with_retry(
    client: dict,
    model: str,
    fallback_model: str,
    system_prompt: str,
    user_prompt: str,
    max_attempts: int = 2,
) -> dict:
    last_error: Exception | None = None
    models_to_try = [model]
    if fallback_model and fallback_model != model:
        models_to_try.append(fallback_model)

    for model_position, current_model in enumerate(models_to_try, start=1):
        current_prompt = user_prompt
        for attempt in range(1, max_attempts + 1):
            try:
                response_text = run_openai_text(
                    client=client,
                    model=current_model,
                    system_prompt=system_prompt,
                    user_prompt=current_prompt,
                )
                return parse_json_text(response_text)
            except Exception as exc:
                last_error = exc
                if should_try_fallback_model(exc) and model_position < len(models_to_try):
                    print(
                        f"Primary model {current_model} hit a retryable upstream/limit error; switching to fallback model {models_to_try[model_position]}.",
                        file=sys.stderr,
                    )
                    break
                current_prompt = (
                    user_prompt
                    + "\n\nImportant: your previous answer was not valid JSON. "
                      "Reply with JSON only, no markdown fences, no explanation."
                )
                if attempt < max_attempts:
                    print(
                        f"AI JSON parse/request failed on model {current_model}, attempt {attempt}/{max_attempts}; retrying.",
                        file=sys.stderr,
                    )
    if last_error is not None:
        raise last_error
    raise RuntimeError("AI JSON request failed unexpectedly.")


def should_try_fallback_model(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = [
        "upstream_connection_error",
        "http 429",
        "rate limit",
        "quota",
        "capacity",
        "http 503",
        "server_error",
    ]
    return any(marker in text for marker in markers)


def parse_json_text(text: str) -> dict:
    candidate = extract_json_candidate(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = repair_common_json_issues(candidate)
        return json.loads(repaired)


def extract_json_candidate(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"Model output did not contain JSON: {text[:200]}")
    return stripped[start:end + 1]


def repair_common_json_issues(text: str) -> str:
    repaired = text.strip()
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", '"').replace("\u2019", '"')
    repaired = repaired.replace("\u300c", '"').replace("\u300d", '"')
    repaired = repaired.replace("\u300e", '"').replace("\u300f", '"')
    repaired = repaired.replace("\r\n", "\n")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r'(?<!\\)\n', r"\\n", repaired)
    return repaired


def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stderr}")
    return result


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc in {"youtu.be", "www.youtu.be"}:
        value = parsed.path.strip("/")
        return value or None
    if "youtube.com" in parsed.netloc:
        query_value = parse_qs(parsed.query).get("v")
        if query_value:
            return query_value[0]
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {"embed", "shorts", "live"}:
            return path_parts[1]
    return None


def is_cookie_decrypt_error(message: str) -> bool:
    return "Failed to decrypt with DPAPI" in message


def is_cookie_permission_error(message: str) -> bool:
    return "Permission denied" in message or "database is locked" in message


def is_cookie_copy_error(message: str) -> bool:
    return "Could not copy Chrome cookie database" in message or "Could not copy Edge cookie database" in message or "Could not copy cookie database" in message


def is_youtube_403_error(message: str) -> bool:
    return "HTTP Error 403" in message or "Sign in to confirm you're not a bot" in message


def is_ssl_certificate_error(exc: Exception) -> bool:
    return "CERTIFICATE_VERIFY_FAILED" in str(exc) or "SSLCertVerificationError" in str(exc)


if __name__ == "__main__":
    raise SystemExit(main())
