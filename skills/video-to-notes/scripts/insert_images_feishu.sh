#!/usr/bin/env bash
# Compatibility wrapper. Optional second argument is the converted Markdown.
set -euo pipefail
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <docx_token> [notes_for_feishu.md] [--dry-run]" >&2
  exit 1
fi
DOC="$1"
shift
NOTES="${1:-notes_for_feishu.md}"
if [ "$#" -gt 0 ]; then shift; fi
exec python "$(dirname "$0")/insert_images_feishu.py" "$DOC" "$NOTES" "$@"
