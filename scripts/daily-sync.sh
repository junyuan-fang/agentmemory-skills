#!/usr/bin/env bash
# Daily sync — catch any uncommitted/unpushed changes left over from cron jobs
# (e.g. push failed earlier due to network blip). Idempotent: silent if clean.
set -uo pipefail

SELF="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO="${AGENTMEMORY_REPO:-$(cd "$SELF/.." && pwd)}"
cd "$REPO" || { echo "[sync] repo missing: $REPO"; exit 1; }

# Stage anything new
git add -A

# Commit if there's anything staged
if ! git diff --cached --quiet; then
    git commit -m "auto sync $(date +%Y-%m-%d)" || true
fi

# Push if local is ahead
LOCAL_AHEAD=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo 0)
if [[ "$LOCAL_AHEAD" -gt 0 ]]; then
    echo "[sync] $LOCAL_AHEAD commit(s) to push"
    git push 2>&1
else
    echo "[sync] $(date '+%H:%M') clean, nothing to push"
fi
