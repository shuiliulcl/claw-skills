"""Score each 1-second window of a video for motion density. Zero LLM tokens;
all local ffmpeg + OpenCV. Output feeds the video-to-notes writer so it can
propose GIF candidates without watching the video.

Approach: sample 1 frame per second at low resolution (256x144 grayscale),
compute absolute frame-to-frame diff, aggregate over sliding N-second windows.
High-diff windows = likely worth a GIF (game demo, UI animation, camera moves);
low-diff = static slides / talking head.

Usage:
    python motion_density.py <video.mp4> [--json <out.json>] [--window 5]
        [--top 20] [--min-score 0]

Output JSON:
    [
      {"start": "00:32:00", "end": "00:32:05", "score": 47.3, "rank": 1},
      ...
    ]
    sorted by score descending, capped at --top entries.

Rule of thumb (tuned against Mass Entity dataset):
    score < 5   — mostly static (slide / title / talking head)
    score 5-15  — moderate motion (UI panels changing / speaker gestures)
    score 15-30 — high motion (demo footage / camera moves)
    score >= 30 — very high motion (particle-heavy demo / rapid UI)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def fmt_ts(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def probe_duration(video: str) -> int:
    """Return duration in seconds (int, floor)."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video],
        capture_output=True, text=True, check=True,
    )
    return int(float(r.stdout.strip()))


def extract_sampled_frames(video: str, duration: int, out_dir: Path) -> list[Path]:
    """Extract 1 frame per second at 256x144 grayscale via one ffmpeg call.
    Much faster than N separate -ss seeks."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "f_%06d.jpg")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video,
        "-vf", "fps=1,scale=256:144:flags=fast_bilinear,format=gray",
        "-q:v", "5", "-y",
        pattern,
    ]
    subprocess.run(cmd, check=True)
    frames = sorted(out_dir.glob("f_*.jpg"))
    return frames


def imread_unicode(path: Path) -> np.ndarray | None:
    """cv2.imread fails on Windows for paths containing non-ASCII characters
    (e.g. Chinese folder names). Use np.fromfile + cv2.imdecode to bypass."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None


def frame_diff_scores(frames: list[Path]) -> list[float]:
    """Return per-second mean absolute pixel diff (0-255 scale)."""
    prev = None
    scores = [0.0]  # first frame has no predecessor
    for p in frames:
        img = imread_unicode(p)
        if img is None:
            scores.append(0.0)
            continue
        if prev is None:
            scores.append(0.0)
        else:
            diff = cv2.absdiff(img, prev)
            scores.append(float(diff.mean()))
        prev = img
    return scores[1:]  # drop the seeded 0.0


def window_scores(per_sec: list[float], window: int) -> list[dict]:
    """Sliding N-second window, mean of per-second diffs. Returns list of
    {start_sec, end_sec, score} for every valid window position."""
    out = []
    n = len(per_sec)
    for i in range(n - window + 1):
        s = sum(per_sec[i:i + window]) / window
        out.append({"start_sec": i, "end_sec": i + window, "score": round(s, 2)})
    return out


def suppress_overlap(windows: list[dict], min_gap: int) -> list[dict]:
    """Non-max suppression: keep highest-scoring windows spaced at least
    min_gap seconds apart. Prevents the same demo scene showing up N times."""
    kept = []
    windows_sorted = sorted(windows, key=lambda w: -w["score"])
    for w in windows_sorted:
        if all(abs(w["start_sec"] - k["start_sec"]) >= min_gap for k in kept):
            kept.append(w)
    return sorted(kept, key=lambda w: -w["score"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--json", help="write full JSON to this path")
    ap.add_argument("--window", type=int, default=5,
                    help="window length in seconds (default 5)")
    ap.add_argument("--top", type=int, default=20,
                    help="max windows to output (default 20)")
    ap.add_argument("--min-score", type=float, default=0,
                    help="drop windows below this score (default 0)")
    ap.add_argument("--tmp", default=None,
                    help="tmp dir for sampled frames (default: video_dir/.motion_tmp)")
    ap.add_argument("--keep-tmp", action="store_true",
                    help="don't delete sampled frames after")
    args = ap.parse_args()

    video = str(Path(args.video).resolve())
    tmp = Path(args.tmp) if args.tmp else Path(video).parent / ".motion_tmp"

    print(f"probing duration of {Path(video).name}...", file=sys.stderr)
    duration = probe_duration(video)
    print(f"  duration: {duration}s ({fmt_ts(duration)})", file=sys.stderr)

    print(f"extracting 1fps 256x144 gray samples...", file=sys.stderr)
    frames = extract_sampled_frames(video, duration, tmp)
    print(f"  {len(frames)} frames sampled", file=sys.stderr)

    print(f"computing per-second frame diffs...", file=sys.stderr)
    per_sec = frame_diff_scores(frames)

    print(f"computing {args.window}s sliding windows...", file=sys.stderr)
    windows = window_scores(per_sec, args.window)

    # Non-max suppression, spacing = window length (no overlap in final output)
    top = suppress_overlap(windows, min_gap=args.window)
    top = [w for w in top if w["score"] >= args.min_score][:args.top]

    # Add HH:MM:SS labels and rank
    for i, w in enumerate(top, 1):
        w["start"] = fmt_ts(w["start_sec"])
        w["end"] = fmt_ts(w["end_sec"])
        w["rank"] = i

    # Print table to stdout
    print(f"# top {len(top)} motion windows ({args.window}s), suppression={args.window}s")
    print(f"{'rank':>4}  {'start':>10}  {'end':>10}  {'score':>7}")
    print("-" * 40)
    for w in top:
        print(f"{w['rank']:>4}  {w['start']:>10}  {w['end']:>10}  {w['score']:>7.2f}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(top, indent=2, ensure_ascii=False)
        )
        print(f"\nfull JSON written to {args.json}", file=sys.stderr)

    if not args.keep_tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
