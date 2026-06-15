"""Clean YouTube auto-caption VTT to plain transcript.

YouTube auto-CC uses a rolling-window format where each cue can repeat the
previous line plus inline per-word timestamps like '<00:00:00.400><c> or</c>'.
We strip the inline timestamps and dedupe consecutive identical lines, then
emit one line per actual speech segment with a leading [hh:mm:ss] timestamp.

Usage:
    python clean_vtt.py <input.vtt> <output.txt>
"""
import re
import sys
from pathlib import Path

CUE_TIME_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.\d+ --> ")
WORD_TS_RE = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d+>")
TAG_RE = re.compile(r"</?c[^>]*>")
ALIGN_RE = re.compile(r" align:.*$")


def fmt_ts(h: int, m: int, s: int) -> str:
    return f"{h:02d}:{m:02d}:{s:02d}"


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__.strip())
        sys.exit(1)
    vtt = Path(sys.argv[1])
    out = Path(sys.argv[2])

    raw = vtt.read_text(encoding="utf-8", errors="replace").splitlines()
    out_lines: list[tuple[str, str]] = []
    cur_ts: str | None = None
    last_text: str = ""

    for line in raw:
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        m = CUE_TIME_RE.match(line)
        if m:
            cur_ts = fmt_ts(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            continue
        if not line.strip():
            continue
        text = WORD_TS_RE.sub("", line)
        text = TAG_RE.sub("", text)
        text = ALIGN_RE.sub("", text)
        text = text.strip()
        if not text:
            continue
        if text == last_text:
            continue
        # Skip prefix-of-previous (rolling window dedup)
        if last_text.startswith(text) and len(text) < len(last_text):
            continue
        out_lines.append((cur_ts or "00:00:00", text))
        last_text = text

    out.write_text(
        "\n".join(f"[{ts}] {tx}" for ts, tx in out_lines),
        encoding="utf-8",
    )
    print(f"Cleaned lines: {len(out_lines)}")
    print(f"Total chars: {sum(len(tx) for _, tx in out_lines)}")
    print(f"Output: {out}")


if __name__ == "__main__":
    main()
