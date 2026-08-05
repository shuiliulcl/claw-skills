"""Score each candidate keyframe on multiple axes so the main thread can
filter out frames the writer would 100% discard anyway (talking head, black
transition, near-duplicate). Zero LLM tokens; all local CV.

Axes:
- full_lap: full-image Laplacian variance (catches full-blur / black / solid)
- min_block_lap: min over 3x3 grid of block Laplacian variance (catches
  partial blur — the failure mode that fooled full_lap on slide_00-00-45)
- entropy: color histogram entropy (low = solid color / near-black)
- face_center_ratio: max face bbox area / center-30% area (high = talking head)
- phash: perceptual hash (used for near-dup dedup across frames)

Usage:
    python frame_quality.py <figures_dir> [--json <out.json>]

Output (stdout, one line per frame, sorted by time):
    <name>  full_lap  min_block  entropy  face  keep_flag  reason
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np


def full_lap_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def min_block_lap(gray: np.ndarray, grid: int = 3) -> float:
    """Split image into grid x grid blocks, return the K-th lowest block score
    (K = 4 for 3x3 grid). Using the min single block false-positives on any
    slide with letterbox / large dark backgrounds — nearly every talk slide.
    K-th lowest tolerates a few dead blocks while still catching partial blur.
    """
    h, w = gray.shape
    bh, bw = h // grid, w // grid
    scores = []
    for r in range(grid):
        for c in range(grid):
            y0, y1 = r * bh, (r + 1) * bh if r < grid - 1 else h
            x0, x1 = c * bw, (c + 1) * bw if c < grid - 1 else w
            block = gray[y0:y1, x0:x1]
            scores.append(float(cv2.Laplacian(block, cv2.CV_64F).var()))
    scores.sort()
    # For 3x3 (9 blocks), take the 4th lowest — tolerates up to 3 dead corners.
    k = max(1, len(scores) // 3 + 1)
    return scores[k - 1]


def median_block_lap(gray: np.ndarray, grid: int = 3) -> float:
    """Median block Laplacian variance — robust central tendency, unaffected
    by black corners or a single bright text region.
    """
    h, w = gray.shape
    bh, bw = h // grid, w // grid
    scores = []
    for r in range(grid):
        for c in range(grid):
            y0, y1 = r * bh, (r + 1) * bh if r < grid - 1 else h
            x0, x1 = c * bw, (c + 1) * bw if c < grid - 1 else w
            block = gray[y0:y1, x0:x1]
            scores.append(float(cv2.Laplacian(block, cv2.CV_64F).var()))
    scores.sort()
    return scores[len(scores) // 2]


def color_entropy(bgr: np.ndarray) -> float:
    """Shannon entropy of the value channel histogram. Low = black/solid."""
    v = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[:, :, 2]
    hist, _ = np.histogram(v, bins=64, range=(0, 256))
    p = hist.astype(np.float64) / max(hist.sum(), 1)
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


_face_cascade = None


def face_center_ratio(gray: np.ndarray) -> float:
    """Largest detected face area / area of the center-30% rectangle.
    >= 1.0 roughly means "a face dominates the center" → talking head.
    Tries two Haar cascades (default + alt2) since stage lighting can defeat
    one but not the other.
    """
    global _face_cascade
    if _face_cascade is None:
        cascade_files = [
            "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt2.xml",
            "haarcascade_profileface.xml",
        ]
        _face_cascade = [
            cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, f))
            for f in cascade_files
        ]

    h, w = gray.shape
    # Center 30% rectangle
    cx0, cx1 = int(w * 0.35), int(w * 0.65)
    cy0, cy1 = int(h * 0.35), int(h * 0.65)
    center_area = (cx1 - cx0) * (cy1 - cy0)

    max_ratio = 0.0
    for casc in _face_cascade:
        faces = casc.detectMultiScale(
            gray, scaleFactor=1.15, minNeighbors=4, minSize=(50, 50)
        )
        for x, y, fw, fh in faces:
            fcx = x + fw / 2
            fcy = y + fh / 2
            if cx0 <= fcx <= cx1 and cy0 <= fcy <= cy1:
                ratio = (fw * fh) / center_area
                if ratio > max_ratio:
                    max_ratio = ratio
    return float(max_ratio)


def perceptual_hash(gray: np.ndarray) -> str:
    """Simple aHash (8x8 average hash). imagehash lib works too but we already
    have gray in memory; keep the dep list minimal.
    """
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    avg = small.mean()
    bits = (small > avg).flatten().astype(np.uint8)
    val = 0
    for b in bits:
        val = (val << 1) | int(b)
    return f"{val:016x}"


def edge_density(gray: np.ndarray) -> float:
    """Fraction of pixels that are Canny edges. High = text/UI/charts/diagrams;
    low = solid backgrounds / talking head / smooth landscape.

    This is the strongest single signal for 'information-rich frame' in
    technical talks where the user learns from UI/code/slide content.
    """
    edges = cv2.Canny(gray, 80, 160)
    return float((edges > 0).mean())


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


# Thresholds tuned against the UE-MCP dataset: 34 writer-picked frames must
# ALL pass; 32 writer-discarded frames should be caught as many as possible.
# Trade recall for zero false-negative kill of a keeper.
KEEP_THRESHOLDS = {
    "median_block_lap": 8.0,      # <8 = most blocks nearly flat, all-frame blur
    "entropy": 1.4,                # <1.4 = essentially monochrome (black end card)
    "edge_low_advisory": 0.015,    # <0.015 → advisory 'low info' flag (talking head / plain background), NOT killed
    "face_center_ratio": 0.5,      # advisory only — face dominates center
    "phash_warn": 8,               # hamming <=8 → advisory 'similar_to', never killed
}


def score_frame(path: Path) -> dict:
    bgr = cv2.imread(str(path))
    if bgr is None:
        return {"name": path.name, "error": "cannot read"}
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return {
        "name": path.name,
        "full_lap": round(full_lap_variance(gray), 1),
        "kth_low_block": round(min_block_lap(gray), 1),
        "median_block": round(median_block_lap(gray), 1),
        "entropy": round(color_entropy(bgr), 2),
        "edge_density": round(edge_density(gray), 4),
        "face": round(face_center_ratio(gray), 2),
        "phash": perceptual_hash(gray),
    }


def apply_filters(records: list[dict]) -> list[dict]:
    """Annotate each record with keep_flag + reason.

    Kill only 100%-certain junk (full blur / near-black). Everything else
    stays; scores go to the writer for cheap ranking. Talking-head detection
    intentionally does not kill — a few speaker shots are useful for context.
    """
    for r in records:
        if "error" in r:
            r["keep"] = False
            r["reason"] = "unreadable"
            continue
        reasons = []
        if r["median_block"] < KEEP_THRESHOLDS["median_block_lap"]:
            reasons.append(f"blur(median_block={r['median_block']:.0f})")
        if r["entropy"] < KEEP_THRESHOLDS["entropy"]:
            reasons.append(f"low_entropy({r['entropy']:.1f})")
        r["keep"] = not reasons
        r["reason"] = ",".join(reasons) if reasons else "ok"
        r["similar_to"] = []

        # advisory flags — never kill, only annotate
        flags = []
        if r["edge_density"] < KEEP_THRESHOLDS["edge_low_advisory"]:
            flags.append(f"low_info(edge={r['edge_density']:.3f})")
        if r["face"] >= KEEP_THRESHOLDS["face_center_ratio"]:
            flags.append(f"talking_head(face={r['face']:.2f})")
        r["advisory"] = ",".join(flags)

    # phash advisory (never kill) — annotate near-duplicates
    kept_indices = [i for i, r in enumerate(records) if r["keep"]]
    for i, idx in enumerate(kept_indices):
        r = records[idx]
        for prev_idx in kept_indices[:i]:
            prev = records[prev_idx]
            if "phash" not in prev or "phash" not in r:
                continue
            d = hamming(r["phash"], prev["phash"])
            if d <= KEEP_THRESHOLDS["phash_warn"]:
                r["similar_to"].append((prev["name"], d))
    return records


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("figures_dir")
    ap.add_argument("--json", help="write full JSON to this path")
    ap.add_argument(
        "--verbose", action="store_true", help="print all frames not just filtered"
    )
    args = ap.parse_args()

    paths = sorted(Path(args.figures_dir).glob("slide_*.jpg"))
    if not paths:
        print(f"no slide_*.jpg under {args.figures_dir}", file=sys.stderr)
        return 1

    records = [score_frame(p) for p in paths]
    records = apply_filters(records)

    keep_ct = sum(1 for r in records if r.get("keep"))
    drop_ct = len(records) - keep_ct

    print(f"# scored {len(records)} frames, keep {keep_ct}, drop {drop_ct}")
    print(f"# thresholds: {KEEP_THRESHOLDS}")
    print()
    header = f"{'frame':32s}  {'full':>7s}  {'med':>6s}  {'entr':>5s}  {'edge':>6s}  {'face':>5s}  {'keep':>4s}  advisory / reason"
    print(header)
    print("-" * len(header))
    for r in records:
        if not args.verbose and r.get("keep") and not r.get("advisory"):
            continue
        if "error" in r:
            print(f"{r['name']:32s}  {'ERR':>7s}  {'-':>6s}  {'-':>5s}  {'-':>6s}  {'-':>5s}  {'0':>4s}  {r['reason']}")
            continue
        note = r["reason"] if not r["keep"] else (r.get("advisory") or "")
        print(
            f"{r['name']:32s}  {r['full_lap']:>7.0f}  {r['median_block']:>6.0f}  "
            f"{r['entropy']:>5.2f}  {r['edge_density']:>6.4f}  {r['face']:>5.2f}  "
            f"{'1' if r['keep'] else '0':>4s}  {note}"
        )

    if args.json:
        Path(args.json).write_text(json.dumps(records, indent=2, ensure_ascii=False))
        print(f"\nfull JSON written to {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
