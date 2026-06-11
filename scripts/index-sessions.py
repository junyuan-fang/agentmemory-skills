#!/usr/bin/env python3
"""
Index cc-connect session JSON files into a SQLite FTS5 database
for fast full-text search.

Usage:
    python3 index-sessions.py [--sessions-dir DIR] [--db DB] [--rebuild]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from _claudecli import ensure_utf8_stdio

DEFAULT_SESSIONS_DIR = Path(
    os.environ.get("AGENTMEMORY_SESSIONS_DIR", "~/.cc-connect/sessions")
).expanduser()
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "sessions.db"


def schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY,
            project TEXT NOT NULL,
            session_id TEXT NOT NULL,
            user_key TEXT,
            user_name TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            agent_type TEXT,
            UNIQUE(project, session_id, timestamp, role)
        );
        CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(timestamp);
        CREATE INDEX IF NOT EXISTS idx_turns_user ON turns(user_key);

        CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
            content,
            content='turns',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE TRIGGER IF NOT EXISTS turns_ai AFTER INSERT ON turns BEGIN
          INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS turns_ad AFTER DELETE ON turns BEGIN
          INSERT INTO turns_fts(turns_fts, rowid, content) VALUES('delete', old.id, old.content);
        END;
        CREATE TRIGGER IF NOT EXISTS turns_au AFTER UPDATE ON turns BEGIN
          INSERT INTO turns_fts(turns_fts, rowid, content) VALUES('delete', old.id, old.content);
          INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
        END;
    """)
    conn.commit()


def index_file(conn: sqlite3.Connection, fp: Path) -> int:
    """Index one cc-connect session JSON file. Returns number of new turns inserted."""
    try:
        # utf-8-sig: 容忍 Windows 工具写入的 BOM
        data = json.loads(fp.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"  skip {fp.name}: {e}", file=sys.stderr)
        return 0

    project = fp.stem.split("_")[0]
    sessions = data.get("sessions") or {}
    user_sessions = data.get("user_sessions") or {}
    user_meta = data.get("user_meta") or {}

    # invert: session_id -> user_key
    session_to_user = {}
    for user_key, sids in user_sessions.items():
        for sid in sids:
            session_to_user[sid] = user_key

    added = 0
    for sid, sess in sessions.items():
        history = sess.get("history") or []
        agent_type = sess.get("agent_type") or ""
        user_key = session_to_user.get(sid, "")
        user_name = (user_meta.get(user_key) or {}).get("user_name", "")

        for turn in history:
            role = turn.get("role") or "?"
            content = turn.get("content") or ""
            ts = turn.get("timestamp") or ""
            if not content:
                continue
            try:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO turns
                       (project, session_id, user_key, user_name, role, content, timestamp, agent_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (project, sid, user_key, user_name, role, content, ts, agent_type),
                )
                if cur.rowcount:
                    added += 1
            except sqlite3.Error as e:
                print(f"  insert err {fp.name} sid={sid}: {e}", file=sys.stderr)
    conn.commit()
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--rebuild", action="store_true",
                    help="drop and rebuild the database from scratch")
    args = ap.parse_args()
    ensure_utf8_stdio()

    args.db.parent.mkdir(parents=True, exist_ok=True)

    if args.rebuild and args.db.exists():
        args.db.unlink()

    if not args.sessions_dir.exists():
        print(f"sessions dir not found: {args.sessions_dir}", file=sys.stderr)
        return 1

    t0 = time.time()
    conn = sqlite3.connect(args.db)
    schema(conn)

    total = 0
    files = sorted(args.sessions_dir.glob("*.json"))
    for fp in files:
        n = index_file(conn, fp)
        if n:
            print(f"  + {n} new turns from {fp.name}")
        total += n

    nturns = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    conn.close()

    elapsed = time.time() - t0
    print(f"\nindexed {len(files)} files, {total} new turns "
          f"({nturns} total in db), {elapsed:.2f}s")
    print(f"db: {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
