#!/usr/bin/env python3
"""
Search conversation history via SQLite FTS5.

Examples:
    query-history.py "auth token"             # keyword search
    query-history.py deploy --since 2026-05   # restrict by date
    query-history.py --session s1             # all turns in a session
    query-history.py --user "o9cq8" --limit 5 # by user, recent N
    query-history.py "权限" --summary          # LLM-summarize matching turns
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

from _claudecli import ensure_utf8_stdio, resolve_date, run_claude

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "sessions.db"


def fts_match(q: str) -> str:
    """Sanitize a free-text query for FTS5 MATCH.
    Wrap each whitespace-separated token in double quotes and OR them.
    """
    tokens = [t for t in re.findall(r"\S+", q) if t]
    if not tokens:
        return ""
    return " ".join('"' + t.replace('"', '""') + '"' for t in tokens)


def fmt_row(r: sqlite3.Row, max_len: int) -> str:
    ts = r["timestamp"][:19].replace("T", " ")
    role = r["role"][:6].ljust(6)
    user = (r["user_name"] or r["user_key"] or "-")[:18].ljust(18)
    content = r["content"].replace("\n", " ⏎ ")
    if len(content) > max_len:
        content = content[:max_len] + "…"
    return f"[{ts}] {role} {user} | {content}"


def claude_summarize(text: str) -> str:
    """Use the claude CLI to summarize. Returns plain text."""
    try:
        result = run_claude(
            "下面是若干条历史对话片段,用中文给出 5 行以内的要点摘要,聚焦在用户的"
            "意图和关键决策上;不要复述对话内容:\n\n" + text,
            timeout=120,
        )
        return result.stdout.strip() or "(claude returned empty)"
    except FileNotFoundError:
        return "[claude CLI not found, install Claude Code to enable --summary]"
    except subprocess.TimeoutExpired:
        return "[summarize timeout]"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("query", nargs="?", help="FTS query (free text)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--since", help="ISO date prefix, e.g. 2026-05 or 2026-05-14")
    ap.add_argument("--until", help="ISO date prefix")
    ap.add_argument("--user", help="filter by user_key substring")
    ap.add_argument("--session", help="filter by session_id")
    ap.add_argument("--role", choices=["user", "assistant"])
    ap.add_argument("--project", help="filter by project name")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--max-len", type=int, default=120,
                    help="max chars to print per content (default 120)")
    ap.add_argument("--summary", action="store_true",
                    help="pipe matched contents into claude to summarize")
    ap.add_argument("--json", action="store_true", help="output raw JSON")
    args = ap.parse_args()
    ensure_utf8_stdio()
    args.since = resolve_date(args.since)
    args.until = resolve_date(args.until)

    if not args.db.exists():
        print(f"db not found: {args.db}\nrun index-sessions.py first.",
              file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    where, params = [], []
    if args.query:
        m = fts_match(args.query)
        if m:
            sql = ("SELECT t.* FROM turns t JOIN turns_fts f ON f.rowid = t.id "
                   "WHERE turns_fts MATCH ?")
            params.append(m)
        else:
            sql = "SELECT * FROM turns WHERE 1=1"
    else:
        sql = "SELECT * FROM turns WHERE 1=1"

    if args.since:
        where.append("timestamp >= ?")
        params.append(args.since)
    if args.until:
        where.append("timestamp < ?")
        params.append(args.until)
    if args.user:
        where.append("user_key LIKE ?")
        params.append(f"%{args.user}%")
    if args.session:
        where.append("session_id = ?")
        params.append(args.session)
    if args.role:
        where.append("role = ?")
        params.append(args.role)
    if args.project:
        where.append("project = ?")
        params.append(args.project)

    if where:
        sql += " AND " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(args.limit)

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("(no matches)")
        return 0

    if args.json:
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
        return 0

    # chronological output
    rows = list(reversed(rows))
    for r in rows:
        print(fmt_row(r, args.max_len))

    if args.summary:
        joined = "\n\n".join(
            f"[{r['timestamp'][:19]}] {r['role']}: {r['content']}" for r in rows
        )
        print("\n--- 摘要 ---")
        print(claude_summarize(joined))

    return 0


if __name__ == "__main__":
    sys.exit(main())
