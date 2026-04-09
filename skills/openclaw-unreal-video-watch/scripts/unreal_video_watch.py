from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class Decision:
    video_id: str
    title: str
    channel: str
    url: str
    published_at: str
    duration_seconds: int | None
    score: int
    status: str
    reasons: list[str]
    notes: list[str]
    query: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan recent Unreal Engine videos and filter low-interest topics.",
    )
    parser.add_argument("--skill-root", required=True, help="Root directory of the skill package.")
    parser.add_argument("--yt-dlp", required=True, help="Path to bundled yt-dlp executable.")
    parser.add_argument("--config", default="", help="Optional path to watch_config.json.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skill_root = Path(args.skill_root).resolve()
    config_path = Path(args.config).resolve() if args.config else skill_root / "config" / "watch_config.json"
    yt_dlp_path = Path(args.yt_dlp).resolve()
    output_dir = skill_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    now = datetime.now()
    cutoff = now - timedelta(hours=int(config["max_age_hours"]))

    yt_dlp_timeout_seconds = int(config.get("yt_dlp_timeout_seconds", 45))
    print(f"[watch] starting candidate collection (timeout={yt_dlp_timeout_seconds}s)", flush=True)
    candidates = collect_candidates(
        yt_dlp_path=yt_dlp_path,
        queries=list(config["queries"]),
        auth_options=build_auth_options(skill_root=skill_root, config=config),
        metadata_enrich_limit=int(config.get("metadata_enrich_limit", 24)),
        no_check_certificates=bool(config.get("no_check_certificates", False)),
        playlist_end=int(config.get("playlist_end", 40)),
        yt_dlp_timeout_seconds=yt_dlp_timeout_seconds,
    )
    print(f"[watch] candidate collection done: {len(candidates)} candidates", flush=True)
    decisions = build_decisions(
        candidates=candidates,
        cutoff=cutoff,
        min_duration_seconds=int(config["min_duration_seconds"]),
        exclude_keywords=list(config["exclude_keywords"]),
        include_hints=list(config["include_hints"]),
        preferred_channels=list(config["preferred_channels"]),
        require_publish_date=bool(config.get("require_publish_date", True)),
    )

    kept = [item for item in decisions if item.status == "keep"]
    rejected = [item for item in decisions if item.status != "keep"]
    kept.sort(key=lambda item: (-item.score, item.published_at, item.title.lower()))
    rejected.sort(key=lambda item: (item.published_at, item.title.lower()), reverse=True)

    timestamp = now.strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"unreal_engine_watch_{timestamp}.json"
    md_path = output_dir / f"unreal_engine_watch_{timestamp}.md"

    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "cutoff": cutoff.isoformat(timespec="seconds"),
        "config_path": str(config_path),
        "kept_count": len(kept),
        "rejected_count": len(rejected),
        "kept": [asdict(item) for item in kept],
        "rejected": [asdict(item) for item in rejected],
    }
    write_json(json_path, payload)
    md_path.write_text(
        build_markdown_report(
            now=now,
            cutoff=cutoff,
            kept=kept[: int(config["top_n"])],
            rejected=rejected[: min(12, len(rejected))],
            json_path=json_path,
        ),
        encoding="utf-8",
    )

    print(f"Kept: {len(kept)}")
    print(f"Rejected: {len(rejected)}")
    print(f"Report: {md_path}")
    print(f"Data: {json_path}")
    return 0


def collect_candidates(
    yt_dlp_path: Path,
    queries: list[str],
    auth_options: list[list[str]],
    metadata_enrich_limit: int,
    no_check_certificates: bool,
    playlist_end: int,
    yt_dlp_timeout_seconds: int,
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for index, query in enumerate(queries, start=1):
        print(f"[watch] search {index}/{len(queries)}: {query}", flush=True)
        result = run_yt_dlp_search(
            yt_dlp_path=yt_dlp_path,
            query=query,
            auth_options=auth_options,
            no_check_certificates=no_check_certificates,
            playlist_end=playlist_end,
            yt_dlp_timeout_seconds=yt_dlp_timeout_seconds,
        )
        entries = result.get("entries") or []
        for entry in entries:
            video_id = str(entry.get("id") or "").strip()
            if not video_id:
                continue
            current = by_id.get(video_id)
            if current is None or score_metadata_richness(entry) > score_metadata_richness(current):
                entry["_query"] = query
                by_id[video_id] = entry
    candidates = list(by_id.values())
    print(f"[watch] starting metadata enrich (limit={metadata_enrich_limit})", flush=True)
    enrich_candidate_metadata(
        yt_dlp_path=yt_dlp_path,
        candidates=candidates,
        auth_options=auth_options,
        limit=metadata_enrich_limit,
        no_check_certificates=no_check_certificates,
        yt_dlp_timeout_seconds=yt_dlp_timeout_seconds,
    )
    return candidates


def run_yt_dlp_search(
    yt_dlp_path: Path,
    query: str,
    auth_options: list[list[str]],
    no_check_certificates: bool,
    playlist_end: int,
    yt_dlp_timeout_seconds: int,
) -> dict[str, Any]:
    attempt_errors: list[str] = []
    attempts = auth_options if auth_options else [[]]
    for auth_args in attempts:
        command = [
            str(yt_dlp_path),
            "--dump-single-json",
            "--no-warnings",
            "--skip-download",
            "--flat-playlist",
            "--playlist-end",
            str(playlist_end),
            *build_tls_args(no_check_certificates),
            *auth_args,
            query,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=yt_dlp_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            attempt_errors.append(f"{describe_auth_args(auth_args)}: timed out after {yt_dlp_timeout_seconds}s")
            continue
        if result.returncode == 0:
            return json.loads(result.stdout)
        error_text = result.stderr.strip() or result.stdout.strip() or f"yt-dlp exited with code {result.returncode}"
        attempt_errors.append(f"{describe_auth_args(auth_args)}: {error_text}")
    raise RuntimeError(build_search_error(query=query, attempt_errors=attempt_errors))


def enrich_candidate_metadata(
    yt_dlp_path: Path,
    candidates: list[dict[str, Any]],
    auth_options: list[list[str]],
    limit: int,
    no_check_certificates: bool,
    yt_dlp_timeout_seconds: int,
) -> None:
    if limit <= 0:
        return

    remaining = limit
    enrich_index = 0
    for entry in candidates:
        if remaining <= 0:
            break
        if not should_enrich_entry(entry):
            continue
        enrich_index += 1
        print(f"[watch] enrich {enrich_index}/{limit}: {entry.get('title') or entry.get('id') or 'unknown'}", flush=True)
        enriched = fetch_video_metadata(
            yt_dlp_path=yt_dlp_path,
            url=pick_url(entry),
            auth_options=auth_options,
            no_check_certificates=no_check_certificates,
            yt_dlp_timeout_seconds=yt_dlp_timeout_seconds,
        )
        if enriched:
            merge_entry_metadata(entry, enriched)
        remaining -= 1


def should_enrich_entry(entry: dict[str, Any]) -> bool:
    wanted_fields = ["upload_date", "duration", "description", "channel", "uploader"]
    return any(not entry.get(field) for field in wanted_fields)


def fetch_video_metadata(
    yt_dlp_path: Path,
    url: str,
    auth_options: list[list[str]],
    no_check_certificates: bool,
    yt_dlp_timeout_seconds: int,
) -> dict[str, Any] | None:
    if not url:
        return None

    attempts = auth_options if auth_options else [[]]
    for auth_args in attempts:
        command = [
            str(yt_dlp_path),
            "--dump-single-json",
            "--no-warnings",
            "--skip-download",
            "--ignore-no-formats-error",
            *build_tls_args(no_check_certificates),
            *auth_args,
            url,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=yt_dlp_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            print(f"[watch] metadata timeout after {yt_dlp_timeout_seconds}s: {url}", flush=True)
            continue
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return None
    return None


def merge_entry_metadata(target: dict[str, Any], enriched: dict[str, Any]) -> None:
    for key in ["upload_date", "duration", "description", "channel", "uploader", "tags", "live_status", "webpage_url"]:
        value = enriched.get(key)
        if value and not target.get(key):
            target[key] = value


def build_tls_args(no_check_certificates: bool) -> list[str]:
    if no_check_certificates:
        return ["--no-check-certificates"]
    return []


def build_auth_options(skill_root: Path, config: dict[str, Any]) -> list[list[str]]:
    options: list[list[str]] = []
    seen_cookie_paths: set[str] = set()
    for cookies_file in iter_cookie_files(skill_root=skill_root, config=config):
        normalized = str(cookies_file).lower()
        if normalized in seen_cookie_paths:
            continue
        seen_cookie_paths.add(normalized)
        if cookies_file.exists():
            options.append(["--cookies", str(cookies_file)])

    for browser in config.get("cookies_from_browser") or []:
        browser_name = str(browser).strip()
        if browser_name:
            options.append(["--cookies-from-browser", browser_name])

    options.append([])
    return options


def iter_cookie_files(skill_root: Path, config: dict[str, Any]) -> list[Path]:
    raw_value = config.get("cookies_file")
    values: list[str]
    if isinstance(raw_value, list):
        values = [str(item).strip() for item in raw_value if str(item).strip()]
    else:
        single_value = str(raw_value or "").strip()
        values = [single_value] if single_value else []

    paths: list[Path] = []
    for value in values:
        expanded = expand_windows_env_vars(value)
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = (skill_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        paths.append(candidate)
    return paths


def expand_windows_env_vars(value: str) -> str:
    expanded = value
    for key, env_value in {
        "%LOCALAPPDATA%": str(Path.home() / "AppData" / "Local"),
        "%APPDATA%": str(Path.home() / "AppData" / "Roaming"),
        "%USERPROFILE%": str(Path.home()),
    }.items():
        expanded = expanded.replace(key, env_value)
    return expanded


def build_search_error(query: str, attempt_errors: list[str]) -> str:
    guidance = (
        "yt-dlp search failed. YouTube is likely requiring authenticated cookies. "
        "Place a Netscape-format cookies file at 'secrets/cookies.txt' inside this skill package, "
        "or update 'cookies_from_browser' in config/watch_config.json to a browser that is already logged into YouTube."
    )
    details = "\n".join(f"- {item}" for item in attempt_errors) if attempt_errors else "- no attempt details captured"
    return f"{guidance}\nQuery: {query}\nAttempts:\n{details}"


def describe_auth_args(auth_args: list[str]) -> str:
    if not auth_args:
        return "anonymous"
    if len(auth_args) >= 2 and auth_args[0] == "--cookies":
        return f"cookies file ({auth_args[1]})"
    if len(auth_args) >= 2 and auth_args[0] == "--cookies-from-browser":
        return f"browser cookies ({auth_args[1]})"
    return "custom auth args"


def score_metadata_richness(entry: dict[str, Any]) -> int:
    fields = ["description", "duration", "channel", "tags", "upload_date", "live_status"]
    return sum(1 for key in fields if entry.get(key))


def build_decisions(
    candidates: list[dict[str, Any]],
    cutoff: datetime,
    min_duration_seconds: int,
    exclude_keywords: list[str],
    include_hints: list[str],
    preferred_channels: list[str],
    require_publish_date: bool,
) -> list[Decision]:
    decisions: list[Decision] = []
    for entry in candidates:
        title = str(entry.get("title") or "").strip()
        description = str(entry.get("description") or "")
        channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
        url = pick_url(entry)
        published = parse_upload_date(entry.get("upload_date"))
        duration = parse_duration(entry.get("duration"))
        live_status = str(entry.get("live_status") or "").strip().lower()
        haystack = f"{title}\n{description}\n{channel}\n{' '.join(entry.get('tags') or [])}".lower()
        reasons: list[str] = []
        notes: list[str] = []

        if not published:
            notes.append("missing publish date")
            if require_publish_date:
                reasons.append("publish date unavailable, recency cannot be verified")
        elif published < cutoff:
            reasons.append(f"older than cutoff ({published.strftime('%Y-%m-%d %H:%M')})")

        if duration is None:
            reasons.append("missing duration")
        elif duration < min_duration_seconds:
            reasons.append(f"too short ({duration}s)")

        if "/shorts/" in url.lower():
            reasons.append("shorts url")

        matched_excludes = [keyword for keyword in exclude_keywords if keyword in haystack]
        if matched_excludes:
            reasons.append("excluded topic: " + ", ".join(matched_excludes[:3]))

        score = compute_score(
            title=title,
            haystack=haystack,
            channel=channel,
            duration=duration,
            include_hints=include_hints,
            preferred_channels=preferred_channels,
        )
        status = "keep" if not reasons else "reject"
        reasons = reasons or ["passes filters"]

        decisions.append(
            Decision(
                video_id=str(entry.get("id") or ""),
                title=title or "untitled",
                channel=channel or "unknown",
                url=url,
                published_at=published.isoformat(timespec="minutes") if published else "unknown",
                duration_seconds=duration,
                score=score,
                status=status,
                reasons=reasons,
                notes=notes,
                query=str(entry.get("_query") or ""),
            )
        )
    return decisions


def compute_score(
    title: str,
    haystack: str,
    channel: str,
    duration: int | None,
    include_hints: list[str],
    preferred_channels: list[str],
) -> int:
    score = 0
    if any(name in channel.lower() for name in preferred_channels):
        score += 5
    score += sum(2 for hint in include_hints if hint in haystack)
    if "unreal engine" in title.lower():
        score += 2
    if duration and 600 <= duration <= 5400:
        score += 1
    return score


def pick_url(entry: dict[str, Any]) -> str:
    webpage_url = str(entry.get("webpage_url") or "").strip()
    if webpage_url:
        return webpage_url
    video_id = str(entry.get("id") or "").strip()
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return ""


def parse_upload_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return datetime.strptime(text, "%Y%m%d")


def parse_duration(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_markdown_report(
    now: datetime,
    cutoff: datetime,
    kept: list[Decision],
    rejected: list[Decision],
    json_path: Path,
) -> str:
    lines = [
        "# Unreal Engine Video Watch",
        "",
        f"- Generated at: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Cutoff: {cutoff.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- JSON: {json_path}",
        "",
        "## Keep",
        "",
    ]
    if not kept:
        lines.append("- No matching videos survived the current filter set.")
    else:
        for index, item in enumerate(kept, start=1):
            lines.extend(
                [
                    f"### {index}. {item.title}",
                    f"- Channel: {item.channel}",
                    f"- Published: {item.published_at}",
                    f"- Duration: {format_duration(item.duration_seconds)}",
                    f"- Score: {item.score}",
                    f"- Query: {item.query}",
                    f"- URL: {item.url}",
                    f"- Why kept: {', '.join(item.reasons)}",
                    f"- Notes: {', '.join(item.notes) if item.notes else 'none'}",
                    "",
                ]
            )

    lines.extend(["## Rejected", ""])
    if not rejected:
        lines.append("- No rejected videos.")
    else:
        for item in rejected:
            lines.extend(
                [
                    f"- {item.title}",
                    f"  - {item.channel} | {item.published_at} | {format_duration(item.duration_seconds)}",
                    f"  - Reason: {', '.join(item.reasons)}",
                    f"  - Notes: {', '.join(item.notes) if item.notes else 'none'}",
                ]
            )
    lines.append("")
    return "\n".join(lines)


def format_duration(value: int | None) -> str:
    if value is None:
        return "unknown"
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
