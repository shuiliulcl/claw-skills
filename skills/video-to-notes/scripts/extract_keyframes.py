"""Scene-detect keyframes from a video, dedupe near-duplicates, rename with absolute timestamps.

Critical: uses sub-second precision floats for ffmpeg -ss extraction.
Integer truncation of pts_time (e.g. 840.5 → 840) shifts to the previous slide.

Pass 3 refines each dedup keeper by probing ±<refine_window>s and picking the
frame with highest Canny edge density — this catches motion-blur / mid-transition
frames that scene detect happened to land on, replacing them with a nearby
stable frame. Skip via --no-refine if you want the raw scene-detected frame.

Usage:
    python extract_keyframes.py <input.mp4> <output_dir> [--threshold 0.3] [--dedup 5.0] [--no-refine]

Output:
    <output_dir>/timestamps.txt — raw scene-change pts_time per line
    <output_dir>/renamed/slide_HH-MM-SS.jpg — deduped, sharpness-refined frames
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def fmt_ts(seconds: float) -> str:
    n = int(seconds)
    return f"{n // 3600:02d}-{(n % 3600) // 60:02d}-{n % 60:02d}"


def _edge_density_of(path: Path) -> float:
    """Return Canny edge density; higher = sharper / less motion blur."""
    import cv2
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return -1.0
    edges = cv2.Canny(img, 80, 160)
    return float((edges > 0).mean())


def _extract_one(video: str, timestamp: float, dst: Path) -> bool:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", str(timestamp),
        "-i", video,
        "-frames:v", "1", "-q:v", "2", "-y",
        str(dst),
    ]
    r = subprocess.run(cmd)
    return r.returncode == 0 and dst.exists()


def refine_sharpness(video: str, timestamp: float, window: float = 3.0,
                     step: float = 1.0) -> float:
    """Probe timestamps in [t-window, t+window] at `step` interval, return the
    timestamp whose extracted frame has the highest Canny edge density.

    Motion-blur / mid-transition frames drop edge density ~50%; a nearby stable
    frame is a much better representative of the same scene. Only replaces if
    the winner beats the anchor's own score by >= 15% — small differences aren't
    worth the churn.
    """
    try:
        import cv2  # noqa: F401  (imported lazily; script still runs without refine)
    except ImportError:
        return timestamp

    tmp = Path(tempfile.mkdtemp(prefix="refine_"))
    try:
        scores: list[tuple[float, float]] = []
        offsets = []
        n_steps = int(window / step)
        for i in range(-n_steps, n_steps + 1):
            offsets.append(i * step)
        for off in offsets:
            ts = timestamp + off
            if ts < 0:
                continue
            probe = tmp / f"probe_{ts:.2f}.jpg"
            if _extract_one(video, ts, probe):
                scores.append((ts, _edge_density_of(probe)))
        if not scores:
            return timestamp
        anchor_score = next((s for ts, s in scores if abs(ts - timestamp) < 1e-6), None)
        best_ts, best_score = max(scores, key=lambda x: x[1])
        if anchor_score is not None and best_score < anchor_score * 1.15:
            return timestamp
        return best_ts
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output_dir")
    ap.add_argument("--threshold", type=float, default=0.3, help="ffmpeg scene threshold (default 0.3)")
    ap.add_argument("--dedup", type=float, default=5.0, help="seconds window to collapse cluster (default 5.0)")
    ap.add_argument("--no-refine", action="store_true", help="skip sharpness refinement pass (Pass 3)")
    ap.add_argument("--refine-window", type=float, default=3.0, help="Pass 3 probe ±window seconds (default 3.0)")
    ap.add_argument("--refine-step", type=float, default=1.0, help="Pass 3 probe step seconds (default 1.0)")
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

    # Pass 3 (optional): refine each keeper to nearest sharper frame within ±window
    if not args.no_refine:
        print(
            f"Pass 3: sharpness refinement (probe ±{args.refine_window}s @ {args.refine_step}s step)",
            file=sys.stderr,
        )
        try:
            import cv2  # noqa: F401
            refined: list[tuple[float, float]] = []
            n_shifted = 0
            for t in kept:
                t2 = refine_sharpness(
                    args.input, t, window=args.refine_window, step=args.refine_step
                )
                if abs(t2 - t) > 0.01:
                    n_shifted += 1
                refined.append((t, t2))
            kept = [t2 for _, t2 in refined]
            print(f"  refined {n_shifted} of {len(refined)} frames to nearby sharper timestamps", file=sys.stderr)
        except ImportError:
            print("  cv2 not installed — skipping Pass 3 (pip install opencv-python<5 to enable)", file=sys.stderr)

    for t in kept:
        ts_label = fmt_ts(t)
        dst = renamed_dir / f"slide_{ts_label}.jpg"
        _extract_one(args.input, t, dst)

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

