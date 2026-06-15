"""Convert tc-video SRT subtitles into the standard transcript.txt format.

tc-video.diezhi.net serves clean SRT files (no per-word timestamps, no rolling
window dedup needed unlike YouTube auto-CC). We just collapse multi-line cues
into single-line `[HH:MM:SS] text` entries.

Usage:
    python srt_to_txt.py <input.srt> <output.txt>
"""
import re
import sys
from pathlib import Path

CUE_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.]\d+ --> "
)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__.strip())
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    raw = src.read_text(encoding="utf-8", errors="replace").splitlines()

    out: list[tuple[str, str]] = []
    cur_ts: str | None = None
    cur_text: list[str] = []
    last_text: str = ""

    def flush() -> None:
        nonlocal cur_text, last_text
        if cur_ts and cur_text:
            text = " ".join(t.strip() for t in cur_text if t.strip())
            if text and text != last_text:
                out.append((cur_ts, text))
                last_text = text
        cur_text = []

    for line in raw:
        m = CUE_TIME_RE.match(line)
        if m:
            flush()
            cur_ts = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
            continue
        if line.strip().isdigit():
            # SRT cue index, skip
            continue
        if not line.strip():
            flush()
            continue
        cur_text.append(line)
    flush()

    dst.write_text(
        "\n".join(f"[{ts}] {tx}" for ts, tx in out),
        encoding="utf-8",
    )
    print(f"Cleaned cues: {len(out)}")
    print(f"Total chars: {sum(len(tx) for _, tx in out)}")
    print(f"Output: {dst}")


if __name__ == "__main__":
    main()
