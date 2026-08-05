"""Scan images referenced in a notes_full.md for potential sharper replacements
nearby. Only FLAGS candidates for human review — never auto-replaces, because
subtle motion blur can mislead heuristics (see phash dedup lesson).

Runs as a Phase 5 (reviewer) helper, catching demo-scene motion-blur that the
Phase 3 anchor-time refine missed because writer picked a *different* frame
from the pool, not the scene-detected one.

Method:
- Probe ±window seconds around each note-referenced frame
- Compare BOTH edge density AND Laplacian variance
- Motion blur reduces both; content-expansion only raises edge_density
- Only flag if BOTH improve significantly → real blur candidate

Usage:
    python check_note_frame_sharpness.py <notes_md> <video.mp4> [--window 5]

Output tiers:
- HIGH   : both edge & lap improve ≥ 2× → real blur, review first
- MEDIUM : both improve 1.3-2× → probably blur or big content change
- (LOW gains suppressed — mostly content-expansion false positives)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from extract_keyframes import _extract_one, _edge_density_of  # noqa: E402


TS_RE = re.compile(r"slide_(\d{2})-(\d{2})-(\d{2})\.jpg")


def _lap_variance(path: Path) -> float:
    """Full-image Laplacian variance — direct sharpness metric."""
    import cv2
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return -1.0
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def probe_range(video: str, timestamp: float, window: float, step: float,
                tmp: Path) -> list[tuple[float, float, float]]:
    """Return list of (ts, edge_density, lap_variance) for probes in the window."""
    n_steps = int(window / step)
    scores: list[tuple[float, float, float]] = []
    for i in range(-n_steps, n_steps + 1):
        ts = timestamp + i * step
        if ts < 0:
            continue
        probe = tmp / f"p_{ts:.2f}.jpg"
        if _extract_one(video, ts, probe):
            scores.append((ts, _edge_density_of(probe), _lap_variance(probe)))
    return scores


def collect_timestamps(notes_md: Path) -> list[tuple[int, str]]:
    text = notes_md.read_text(encoding="utf-8")
    seen: set[int] = set()
    frames: list[tuple[int, str]] = []
    for m in TS_RE.finditer(text):
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        secs = h * 3600 + mi * 60 + s
        if secs in seen:
            continue
        seen.add(secs)
        frames.append((secs, f"{m.group(1)}:{m.group(2)}:{m.group(3)}"))
    frames.sort()
    return frames


def _fmt_hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("notes_md")
    ap.add_argument("video")
    ap.add_argument("--window", type=float, default=5.0)
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--min-gain", type=float, default=1.3,
                    help="minimum min(edge_gain, lap_gain) to report (default 1.3)")
    ap.add_argument("--high-gain", type=float, default=2.0,
                    help="HIGH tier: both edge & lap gain >= this (default 2.0)")
    ap.add_argument("--anchor-min-edge", type=float, default=0.015,
                    help="ignore anchors below this edge density (title slides etc)")
    args = ap.parse_args()

    notes = Path(args.notes_md)
    if not notes.exists():
        print(f"error: {notes} not found", file=sys.stderr)
        return 1

    frames = collect_timestamps(notes)
    if not frames:
        print(f"no slide_HH-MM-SS.jpg references in {notes}", file=sys.stderr)
        return 0

    print(f"# scanning {len(frames)} frames from {notes.name}", file=sys.stderr)
    print(f"# window ±{args.window}s @ {args.step}s step")
    print(f"# HIGH if min(edge,lap) gain >= {args.high_gain}x, MEDIUM if >= {args.min_gain}x")
    print(f"# ignoring anchors with edge_density < {args.anchor_min_edge}")
    print()

    tmp = Path(tempfile.mkdtemp(prefix="notecheck_"))
    try:
        rows: list[tuple[str, str, float, float, float, float, float, float]] = []
        skipped = 0
        for secs, ts_str in frames:
            probes = probe_range(args.video, float(secs), args.window, args.step, tmp)
            anchor = next((p for p in probes if abs(p[0] - secs) < 1e-6), None)
            if anchor is None:
                continue
            a_ts, a_edge, a_lap = anchor
            if a_edge < args.anchor_min_edge:
                skipped += 1
                continue
            # winner = max by edge (matches Phase 3 refine); check lap separately
            best_edge = max(probes, key=lambda p: p[1])
            b_ts, b_edge, b_lap = best_edge
            if abs(b_ts - a_ts) < 0.01:
                continue
            edge_gain = b_edge / max(a_edge, 1e-6)
            lap_gain = b_lap / max(a_lap, 1e-6)
            min_gain = min(edge_gain, lap_gain)
            if min_gain < args.min_gain:
                continue

            tier = "HIGH" if min_gain >= args.high_gain else "MED "
            rows.append((tier, ts_str, a_edge, a_lap, b_ts, b_edge, b_lap, min_gain))

        # sort by tier (HIGH first) then gain desc
        rows.sort(key=lambda r: (0 if r[0] == "HIGH" else 1, -r[7]))

        if not rows:
            print(f"clean — {len(frames) - skipped} content frames checked, "
                  f"no suspicious sharpness gaps.")
            if skipped:
                print(f"({skipped} low-edge anchors skipped: title slides / not-yet-shown)")
            return 0

        header = f"{'tier':>5s}  {'anchor':>10s}  {'a_edge':>7s} {'a_lap':>6s}    {'new_ts':>8s}  {'n_edge':>7s} {'n_lap':>6s}  {'min_gain':>8s}"
        print(header)
        print("-" * len(header))
        for tier, ts, a_e, a_l, b_ts, b_e, b_l, mg in rows:
            print(f"{tier:>5s}  {ts:>10s}  {a_e:7.4f} {a_l:6.0f}    {_fmt_hms(b_ts):>8s}  {b_e:7.4f} {b_l:6.0f}  {mg:7.2f}x")

        high = sum(1 for r in rows if r[0] == "HIGH")
        med = sum(1 for r in rows if r[0] == "MED ")
        print()
        print(f"{high} HIGH (likely real blur — review these first)")
        print(f"{med} MED  (may be blur or big content change — visual check)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
