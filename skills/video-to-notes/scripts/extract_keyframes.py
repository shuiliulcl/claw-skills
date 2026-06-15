"""Scene-detect keyframes from a video, dedupe near-duplicates, rename with absolute timestamps.

Critical: uses sub-second precision floats for ffmpeg -ss extraction.
Integer truncation of pts_time (e.g. 840.5 → 840) shifts to the previous slide.

Usage:
    python extract_keyframes.py <input.mp4> <output_dir> [--threshold 0.3] [--dedup 5.0]

Output:
    <output_dir>/timestamps.txt — raw scene-change pts_time per line
    <output_dir>/renamed/slide_HH-MM-SS.jpg — deduped frames at clean filenames
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def fmt_ts(seconds: float) -> str:
    n = int(seconds)
    return f"{n // 3600:02d}-{(n % 3600) // 60:02d}-{n % 60:02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output_dir")
    ap.add_argument("--threshold", type=float, default=0.3, help="ffmpeg scene threshold (default 0.3)")
    ap.add_argument("--dedup", type=float, default=5.0, help="seconds window to collapse cluster (default 5.0)")
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = out
    renamed_dir = out / "renamed"
    # Cleanup old products: if a previous run produced different dedup keep set
    # (e.g. video resolution changed → scene threshold hits different frames),
    # leftover slide_*.jpg from prior run will silently mix into new output.
    # Wipe renamed/ before re-extracting.
    if renamed_dir.exists():
        for f in renamed_dir.glob("slide_*.jpg"):
            f.unlink()
        print(f"  cleaned old slide_*.jpg in {renamed_dir}", file=sys.stderr)
    renamed_dir.mkdir(exist_ok=True)
    timestamps_file = out / "timestamps.txt"

    # Pass 1: detect scene changes, output raw scene_NNNN.jpg + collect pts_time
    print(f"Pass 1: scene detection (threshold={args.threshold}) on {args.input}", file=sys.stderr)
    cmd = [
        "ffmpeg", "-hide_banner", "-i", args.input,
        "-vf", f"select='gt(scene,{args.threshold})',showinfo",
        "-vsync", "vfr", "-q:v", "2",
        str(raw_dir / "scene_%04d.jpg"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # showinfo lines on stderr: "Parsed_showinfo_1 ... pts_time:570.5 ..."
    pts_re = re.compile(r"pts_time:([0-9.]+)")
    timestamps = [float(m) for m in pts_re.findall(proc.stderr)]
    timestamps_file.write_text("\n".join(str(t) for t in timestamps), encoding="utf-8")
    print(f"  raw scene candidates: {len(timestamps)}", file=sys.stderr)

    # Pass 2: dedup within window, re-extract with sub-second precision
    print(f"Pass 2: dedup (window={args.dedup}s) and re-extract at sub-second precision", file=sys.stderr)
    kept: list[float] = []
    last = -1e9
    for t in timestamps:
        if t - last < args.dedup:
            continue
        kept.append(t)
        last = t

    for t in kept:
        ts_label = fmt_ts(t)
        dst = renamed_dir / f"slide_{ts_label}.jpg"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(t),
            "-i", args.input,
            "-frames:v", "1", "-q:v", "2", "-y",
            str(dst),
        ]
        subprocess.run(cmd, check=True)

    # Cleanup raw scene_NNNN.jpg (we have renamed copies)
    for f in raw_dir.glob("scene_*.jpg"):
        f.unlink()

    print(f"  kept {len(kept)} of {len(timestamps)}", file=sys.stderr)
    print(f"  output: {renamed_dir}", file=sys.stderr)
    print(f"\nTime distribution (10-min bands):", file=sys.stderr)
    bands = [0, 600, 1200, 1800, 2400, 3000, 3600, 99999]
    band_names = ["00-10m", "10-20m", "20-30m", "30-40m", "40-50m", "50-60m", "60+"]
    for i, name in enumerate(band_names):
        n = sum(1 for t in kept if bands[i] <= t < bands[i + 1])
        if n:
            print(f"  {name}: {n}", file=sys.stderr)


if __name__ == "__main__":
    main()
