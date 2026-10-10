"""Insert Markdown images using unique timestamp captions and a local retry journal.
Run with --dry-run first. An uncertain pending request requires manual reconciliation.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def collect_items(notes):
    text = notes.read_text(encoding="utf-8")
    items = []
    pattern = r"^!\[[^\]]*\]\(([^\n]+)\)\s*\n\s*\*([^\n]+)\*\s*$"
    for match in re.finditer(pattern, text, re.M):
        path = (notes.parent / match[1].strip().strip("<>")).resolve()
        caption = match[2].strip()
        if not re.search(r"来源\s+\d{2}:\d{2}:\d{2}", caption):
            raise ValueError(f"Caption missing timestamp: {caption}")
        if text.count(caption) != 1:
            raise ValueError(f"Caption is not unique: {caption}")
        if not path.is_file():
            raise ValueError(f"Missing image: {path}")
        key = hashlib.sha256((caption + "\0" + str(path)).encode()).hexdigest()
        items.append({"path": str(path), "caption": caption, "key": key,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    expected = len(re.findall(r"!\[", text))
    if len(items) != expected:
        raise ValueError("Some images have unsupported syntax or missing italic captions")
    return items


def save(path, state):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("doc")
    ap.add_argument("notes", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state", type=Path)
    args = ap.parse_args()
    notes_dir = args.notes.resolve().parent
    items = collect_items(args.notes.resolve())
    for item in items:
        item["upload_path"] = Path(item["path"]).relative_to(notes_dir).as_posix()
    if args.dry_run:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return
    cli = shutil.which("lark-cli")
    if not cli:
        raise RuntimeError("lark-cli not found")
    state_path = args.state or args.notes.with_name("feishu-images-" + hashlib.sha256(args.doc.encode()).hexdigest()[:12] + ".json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"doc": args.doc, "items": {}}
    if state["doc"] != args.doc:
        raise ValueError("Journal belongs to a different document")
    for item in items:
        old = state["items"].get(item["key"])
        if old and (old["status"] != "done" or old["sha256"] != item["sha256"]):
            raise RuntimeError("Pending request or changed image; reconcile remote document and journal before retrying")
    inserted = skipped = 0
    for item in items:
        if item["key"] in state["items"]:
            skipped += 1
            continue
        state["items"][item["key"]] = {"status": "pending", "sha256": item["sha256"], "caption": item["caption"]}
        save(state_path, state)
        result = subprocess.run([cli, "docs", "+media-insert", "--doc", args.doc,
            "--selection-with-ellipsis", item["caption"], "--before", "--file", item["upload_path"],
            "--type", "image", "--width", "720", "--height", "405", "--as", "user", "--jq", ".ok"],
            capture_output=True, text=True, encoding="utf-8", cwd=notes_dir)
        if result.returncode or result.stdout.strip().splitlines()[-1:] != ["true"]:
            raise RuntimeError("Insertion not confirmed; pending journal retained. " + result.stderr[-1000:])
        state["items"][item["key"]]["status"] = "done"
        save(state_path, state)
        inserted += 1
        print(f"Confirmed {inserted + skipped}/{len(items)}: {Path(item['path']).name}", flush=True)
    print(f"Inserted {inserted}; already confirmed {skipped}; total {len(items)}")


if __name__ == "__main__":
    main()
