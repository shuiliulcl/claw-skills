#!/usr/bin/env bash
# Insert local images into a feishu docx at caption anchor positions.
# Each image gets width=720 height=405 (16:9) — must match the source aspect to avoid white padding.
#
# Usage:
#   1. Edit ITEMS below: each line is "<caption text>\t<local image path>"
#      Caption must be unique within the doc (use timestamps for uniqueness)
#      Image path must be relative to cwd
#   2. cd to your video-notes/<slug>/ project dir
#   3. ./insert_images_feishu.sh <docx_token>
#
# Prerequisites:
#   - markdown already imported as docx and overwritten (clears placeholder images)
#   - lark-cli authenticated as user

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <docx_token>"
  echo "  Run from the project working dir (where image paths are relative to)"
  exit 1
fi

DOC="$1"

# (caption, image_path) pairs — caption MUST be unique in doc
# Replace these with actual values from your video-notes
ITEMS=(
"Trace Hit demo · 150,000 projectiles / sec · 来源 00:08:45	figures_full/renamed/slide_00-08-45.jpg"
"Multi-Trace demo · 24,000 projectiles / sec · 来源 00:08:54	figures_full/renamed/slide_00-08-54.jpg"
# ... add the rest
)

i=0
total=${#ITEMS[@]}
for entry in "${ITEMS[@]}"; do
  i=$((i+1))
  caption="${entry%%	*}"
  img="${entry#*	}"
  echo ">>> [$i/$total] $img  ←  '$caption'"

  if [ ! -f "$img" ]; then
    echo "    SKIP: $img not found"
    continue
  fi

  ok=$(lark-cli docs +media-insert \
    --doc "$DOC" \
    --selection-with-ellipsis "$caption" \
    --before \
    --file "$img" \
    --type image \
    --width 720 \
    --height 405 \
    --as user \
    --jq '.ok' 2>/dev/null | tr -d '"' | tr -d '[:space:]')

  if [ "$ok" != "true" ]; then
    echo "    ERROR: ok=$ok"
    exit 1
  fi
  echo "    inserted ✓"
done

echo ""
echo "Done — $total images inserted with 720x405 dimensions."
