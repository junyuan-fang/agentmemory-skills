#!/usr/bin/env python3
"""
Export indexed conversation history to markdown files, organized by date.

Usage:
    archive-session.py                          # archive today's turns
    archive-session.py --date 2026-05-14
    archive-session.py --all                    # all history
    archive-session.py --since 2026-05-01
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from _claudecli import ensure_utf8_stdio, resolve_date

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "sessions.db"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "archive"


def render_md(date_str: str, rows: list[sqlite3.Row]) -> str:
    out = [f"# 对话归档 — {date_str}", ""]
    by_session = defaultdict(list)
    for r in rows:
        by_session[(r["project"], r["session_id"], r["user_name"] or r["user_key"])].append(r)

    for (project, sid, user), turns in by_session.items():
        out.append(f"## `{project}` / session `{sid}` / user `{user}`")
        out.append("")
        for t in turns:
            ts = t["timestamp"][11:19]
            role = "🧑" if t["role"] == "user" else "🤖"
            out.append(f"### {role} {role} {ts}")
            out.append("")
            out.append(t["content"])
            out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--date", help="YYYY-MM-DD (default: today)")
    g.add_argument("--since", help="YYYY-MM-DD (archive each day from this date to today)")
    g.add_argument("--all", action="store_true",
                   help="archive every day that has turns")
    args = ap.parse_args()
    ensure_utf8_stdio()
    args.date = resolve_date(args.date)
    args.since = resolve_date(args.since)

    if not args.db.exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if args.all:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT substr(timestamp,1,10) FROM turns ORDER BY 1")]
    elif args.since:
        start = dt.date.fromisoformat(args.since)
        end = dt.date.today()
        dates = [(start + dt.timedelta(days=i)).isoformat()
                 for i in range((end - start).days + 1)]
    else:
        dates = [args.date or dt.date.today().isoformat()]

    written = 0
    for d in dates:
        rows = conn.execute(
            "SELECT * FROM turns WHERE substr(timestamp,1,10)=? ORDER BY timestamp",
            (d,),
        ).fetchall()
        if not rows:
            continue
        out_file = args.out / f"{d}.md"
        out_file.write_text(render_md(d, rows), encoding="utf-8")
        print(f"  + {out_file.relative_to(args.out.parent)}  ({len(rows)} turns)")
        written += 1

    print(f"\nwrote {written} archive file(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
