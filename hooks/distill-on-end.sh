#!/usr/bin/env bash
# SessionEnd hook — "关闭即沉淀".
# Claude Code runs this when a session ends, piping a JSON object on stdin
# that includes `transcript_path` and `session_id`. We index that transcript
# and distill skills from it. Runs detached so closing Claude never blocks.
#
# Install: see hooks/README.md (register under settings.json "hooks" → "SessionEnd").
set -uo pipefail

SELF="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO="${AGENTMEMORY_REPO:-$(cd "$SELF/.." && pwd)}"
PY="${PYTHON:-python3}"
LOG="$REPO/data/cron.log"

INPUT="$(cat)"
read -r TRANSCRIPT SID < <(
  printf '%s' "$INPUT" | "$PY" -c \
    'import json,sys; o=json.load(sys.stdin); print(o.get("transcript_path",""), o.get("session_id",""))' \
    2>/dev/null
)
[ -z "${TRANSCRIPT:-}" ] && exit 0

mkdir -p "$REPO/data"
# Detach: index the just-ended transcript, then distill skills from it.
# extract-skill.py calls `claude -p`, so we background it to avoid blocking exit.
{
  echo "[distill $(date '+%F %T')] session=$SID transcript=$TRANSCRIPT"
  "$PY" "$REPO/scripts/index-sessions.py" --file "$TRANSCRIPT"
  # Comment the next line out if per-session extraction feels too heavy;
  # the daily cron extract will still pick everything up.
  [ -n "${SID:-}" ] && "$PY" "$REPO/scripts/extract-skill.py" --session "$SID"
} >> "$LOG" 2>&1 &

exit 0
