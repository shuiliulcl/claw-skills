"""Resilient YouTube video download that filters bad Google CDN edge hosts.

Some googlevideo edge servers (e.g. sn-ojnpo5-c3 observed 2026-08) are
persistently unreachable from certain networks — yt-dlp / aria2c / curl all
timeout because the bad host is embedded in the signed URL.

This script:
  1. Calls yt-dlp -g to get the signed URL
  2. Extracts the host from the URL
  3. If host is in a known-bad set, retries (yt-dlp re-signs to a random edge)
  4. If host is fresh, uses curl -sSL (follow 302) to download

Usage:
    python resilient_ytdlp_download.py <youtube_url> <output_mp4> \\
        [--format 137/299/298] [--attempts 8] [--min-size 50]

    # bad hosts persist across invocations if you record them; edit BAD_HOSTS.

Requires: yt-dlp on PATH, curl on PATH.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

# Persistently unreachable Google CDN edges observed in the wild.
# Add hosts here as you encounter them. YouTube URL signing is random, so
# eventually a rerun will land on a good edge.
BAD_HOSTS = {
    "rr1---sn-ojnpo5-c3.googlevideo.com",
}

DENO = None


def find_deno() -> str:
    """Locate deno.exe: cwd-local bin > skill-shared bin > PATH."""
    global DENO
    if DENO:
        return DENO
    candidates = [
        Path("./bin/deno.exe").resolve(),
        Path.home() / ".claude/skills/video-to-notes/bin/deno.exe",
    ]
    for p in candidates:
        if p.exists():
            DENO = str(p)
            return DENO
    DENO = "deno"  # last resort: expect on PATH
    return DENO


def resolve_url(youtube_url: str, fmt: str) -> str | None:
    """Ask yt-dlp for a direct download URL."""
    deno = find_deno()
    r = subprocess.run(
        ["yt-dlp", "--js-runtimes", f"deno:{deno}", "-f", fmt, "-g", youtube_url],
        capture_output=True, text=True, timeout=90,
    )
    urls = [u for u in r.stdout.strip().splitlines() if u.startswith("http")]
    return urls[-1] if urls else None


def host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)/", url)
    return m.group(1) if m else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("youtube_url")
    ap.add_argument("output")
    ap.add_argument("--format", default="137/299/298",
                    help="yt-dlp format spec (default: 1080p30 mp4 / 1080p60 / 720p60)")
    ap.add_argument("--attempts", type=int, default=8)
    ap.add_argument("--min-size", type=int, default=50,
                    help="Minimum expected file size in MB")
    args = ap.parse_args()

    out = Path(args.output)
    min_bytes = args.min_size * 1024 * 1024

    for attempt in range(1, args.attempts + 1):
        print(f"[attempt {attempt}/{args.attempts}] resolving URL...")
        url = resolve_url(args.youtube_url, args.format)
        if not url:
            print("  no url returned by yt-dlp"); time.sleep(5); continue
        host = host_of(url)
        print(f"  host: {host}")
        if host in BAD_HOSTS:
            print("  BAD host, retrying..."); time.sleep(3); continue
        print(f"  curling -> {out}...")
        subprocess.run(
            ["curl", "-sSL", "--connect-timeout", "20", "--max-time", "1200",
             "-o", str(out), url],
            timeout=1500,
        )
        size = out.stat().st_size if out.exists() else 0
        if size > min_bytes:
            print(f"[ok] {size // (1024*1024)} MB")
            return
        print(f"  failed (file {size} B); retry")
        if out.exists() and size < 1024:
            out.unlink()

    print("[fail] all attempts exhausted", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
