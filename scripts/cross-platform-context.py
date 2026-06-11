#!/usr/bin/env python3
"""
Inject "what this same person said on OTHER platforms recently" into the
current Claude session.

How identity mapping works:
    `_tools/data/identities.json` maps a real person to all their platform
    user_keys (so we can recognize "alice@telegram == alice@slack").
    Format:
    {
      "alice": ["telegram:dm:123", "slack:U0ABC"],
      "bob":   ["wechat:dm:xxxx"]
    }

Usage:
    cross-platform-context.py --user-key <session_user>      # standard
    cross-platform-context.py --person alice                 # by name
    cross-platform-context.py --user-key <key> --raw         # don't summarize
    cross-platform-context.py --user-key <key> --days 30

Designed to be called by a Claude Code SessionStart hook. The output (markdown)
is appended to the agent's context. If the user is the only person in their
identity bucket (no cross-platform history), prints nothing — silent no-op.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from _claudecli import ensure_utf8_stdio, run_claude

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "sessions.db"
IDENTITIES = REPO_ROOT / "data" / "identities.json"


def load_identities() -> dict:
    if not IDENTITIES.exists():
        return {}
    try:
        return json.loads(IDENTITIES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_person(user_key: str, identities: dict) -> tuple[str | None, list[str]]:
    """Given a user_key, return (person_name, list of all their user_keys)."""
    for person, keys in identities.items():
        if user_key in keys:
            return person, list(keys)
    return None, [user_key]


def gather_other_platform_turns(conn, user_keys: list[str], current_key: str,
                                days: int, limit: int) -> list:
    """Get recent turns from same person but NOT the current platform session."""
    if not user_keys:
        return []
    since = (dt.datetime.now() - dt.timedelta(days=days)).isoformat()
    placeholders = ",".join("?" for _ in user_keys)
    sql = (f"SELECT timestamp, role, content, user_key FROM turns "
           f"WHERE user_key IN ({placeholders}) AND user_key != ? "
           f"AND timestamp >= ? "
           f"ORDER BY timestamp DESC LIMIT ?")
    return conn.execute(sql, [*user_keys, current_key, since, limit]).fetchall()


def summarize(transcript: str) -> str:
    try:
        result = run_claude(
            "下面是用户最近在其他平台跟 AI 的对话,用 5 行以内的中文摘要,"
            "聚焦在用户的近期意图、关心的话题、未完成的任务:\n\n" + transcript,
            timeout=120,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[summarize failed: {e}]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--user-key", help="this session's user_key")
    g.add_argument("--person", help="known person name (from identities.json)")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--raw", action="store_true",
                    help="show raw transcript instead of LLM summary")
    args = ap.parse_args()
    ensure_utf8_stdio()

    if not args.db.exists():
        return 0  # silent no-op if no index yet

    identities = load_identities()

    if args.person:
        keys = identities.get(args.person, [])
        if not keys:
            return 0
        current = keys[0]  # arbitrary, just for filter
    else:
        person, keys = find_person(args.user_key, identities)
        current = args.user_key

    if len(keys) <= 1:
        # only one platform → no cross-platform context to inject
        return 0

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = gather_other_platform_turns(conn, keys, current, args.days, args.limit)
    if not rows:
        return 0

    transcript = "\n".join(
        f"[{r['timestamp'][:16]}] {r['role']} ({r['user_key']}): {r['content']}"
        for r in reversed(rows)
    )

    print("## 来自其他平台的近期上下文")
    print()
    if args.raw:
        print("```")
        print(transcript[:4000])
        print("```")
    else:
        summary = summarize(transcript)
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
