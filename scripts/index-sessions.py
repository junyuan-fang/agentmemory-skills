#!/usr/bin/env python3
"""
Index Claude Code's own session transcripts into a SQLite FTS5 database
for fast full-text search.

Source = Claude Code's native transcripts, which it writes for every session:
    ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
Each line is one event; we keep `user` / `assistant` messages and pull out
their human-readable text (skipping thinking blocks, tool calls, tool results).
Nothing to export — if you use Claude Code, these files already exist.

Usage:
    index-sessions.py                       # index every project transcript
    index-sessions.py --file PATH.jsonl     # index one transcript (used by the
                                            #   SessionEnd hook: distill-on-end.sh)
    index-sessions.py --projects-dir DIR    # override ~/.claude/projects
    index-sessions.py [--db DB] [--rebuild] [--include-sidechains]
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

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root
DEFAULT_PROJECTS_DIR = Path(
    os.environ.get("AGENTMEMORY_PROJECTS_DIR", "~/.claude/projects")
).expanduser()
DEFAULT_DB = REPO_ROOT / "data" / "sessions.db"


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


def extract_text(content) -> str:
    """Pull human-readable text out of a Claude Code message `content`.

    - user content is usually a plain string.
    - it can also be a list of blocks; we keep `text` blocks and plain strings,
      and drop tool_result / tool_use / thinking / image blocks.
    - assistant content is a list of blocks: keep `text`, drop thinking & tool_use.
    """
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(p for p in parts if p).strip()


def index_file(conn: sqlite3.Connection, fp: Path, include_sidechains: bool) -> int:
    """Index one Claude Code transcript (.jsonl). Returns new turns inserted."""
    project = fp.parent.name.lstrip("-").replace("-", "/")  # fallback
    session_id = fp.stem
    cwd_seen = None

    rows_to_add = []
    try:
        # utf-8-sig: 容忍 Windows 工具写入的 BOM,否则首行 JSON 解析失败被跳过
        for line in fp.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") not in ("user", "assistant"):
                continue
            if o.get("isSidechain") and not include_sidechains:
                continue
            if cwd_seen is None and o.get("cwd"):
                cwd_seen = o["cwd"]
            msg = o.get("message") or {}
            role = msg.get("role") or o.get("type")
            text = extract_text(msg.get("content"))
            if not text:
                continue
            rows_to_add.append((role, text, o.get("timestamp") or "",
                                o.get("sessionId") or session_id))
    except Exception as e:
        print(f"  skip {fp.name}: {e}", file=sys.stderr)
        return 0

    if cwd_seen:
        project = Path(cwd_seen).name or project

    added = 0
    for role, text, ts, sid in rows_to_add:
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO turns
                   (project, session_id, user_key, user_name, role, content, timestamp, agent_type)
                   VALUES (?, ?, '', '', ?, ?, ?, 'claude-code')""",
                (project, sid, role, text, ts),
            )
            if cur.rowcount:
                added += 1
        except sqlite3.Error as e:
            print(f"  insert err {fp.name}: {e}", file=sys.stderr)
    conn.commit()
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR,
                    help="Claude Code projects dir (default ~/.claude/projects)")
    ap.add_argument("--file", type=Path,
                    help="index a single transcript .jsonl (used by SessionEnd hook)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--rebuild", action="store_true",
                    help="drop and rebuild the database from scratch")
    ap.add_argument("--include-sidechains", action="store_true",
                    help="also index subagent (sidechain) transcripts")
    args = ap.parse_args()
    ensure_utf8_stdio()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.rebuild and args.db.exists():
        args.db.unlink()

    if args.file:
        files = [args.file]
    else:
        if not args.projects_dir.exists():
            print(f"projects dir not found: {args.projects_dir}\n"
                  f"is Claude Code installed? override with --projects-dir.",
                  file=sys.stderr)
            return 1
        files = sorted(args.projects_dir.glob("*/*.jsonl"))

    t0 = time.time()
    conn = sqlite3.connect(args.db)
    schema(conn)

    total = 0
    for fp in files:
        if not fp.exists():
            print(f"  not found: {fp}", file=sys.stderr)
            continue
        n = index_file(conn, fp, args.include_sidechains)
        if n:
            print(f"  + {n} new turns from {fp.parent.name}/{fp.name}")
        total += n

    nturns = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    conn.close()

    elapsed = time.time() - t0
    print(f"\nindexed {len(files)} transcript(s), {total} new turns "
          f"({nturns} total in db), {elapsed:.2f}s")
    print(f"db: {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
