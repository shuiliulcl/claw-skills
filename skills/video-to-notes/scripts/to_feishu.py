"""Convert an Obsidian-flavored note into a feishu-clean markdown.

Obsidian flavor (input):
- YAML frontmatter at top with at least `feishu_wiki` field
- Cross-links use `[[<slug>/notes_full|Display Text]]` syntax

Feishu flavor (output):
- No frontmatter (feishu renders YAML as ugly code block)
- `[[wikilinks]]` resolved to `[Display Text](<feishu_wiki_url>)` via registry

Usage:
    python to_feishu.py <input.md> <output.md> [--registry <path>]
        # default registry: D:/Obsidian Vault/工具/video-notes/registry.json

Registry format:
    {
      "ue-projectiles": {
        "title": "...",
        "feishu_wiki": "https://papergames.feishu.cn/wiki/...",
        "publish_date": "..."
      },
      ...
    }

If a wikilink target's slug is not in registry, the link is left as plain text
with a warning printed to stderr.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path("D:/Obsidian Vault/工具/video-notes/registry.json")

# Match [[slug]] or [[slug|Display]] or [[slug/notes_full|Display]] etc.
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2].lstrip("\n")


def resolve_slug(target: str) -> str:
    # Obsidian wikilinks may include path: "ue-projectiles/notes_full"
    # We treat the first path component as the slug.
    return target.split("/", 1)[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = ap.parse_args()

    if not args.registry.exists():
        print(f"[Error] registry not found: {args.registry}", file=sys.stderr)
        print("Create it with at least one entry. See docstring for format.", file=sys.stderr)
        sys.exit(1)

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    text = Path(args.input).read_text(encoding="utf-8")
    text = strip_frontmatter(text)

    missing: set[str] = set()
    resolved: int = 0

    def replace(m: re.Match) -> str:
        nonlocal resolved
        target = m.group(1).strip()
        display = (m.group(2) or target).strip()
        slug = resolve_slug(target)
        entry = registry.get(slug)
        if not entry or not entry.get("feishu_wiki"):
            missing.add(slug)
            return display  # fall back to plain text
        resolved += 1
        return f"[{display}]({entry['feishu_wiki']})"

    text = WIKILINK_RE.sub(replace, text)
    Path(args.output).write_text(text, encoding="utf-8")

    print(f"Resolved {resolved} wikilinks")
    if missing:
        print(f"[Warning] {len(missing)} slug(s) not in registry: {sorted(missing)}", file=sys.stderr)
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
