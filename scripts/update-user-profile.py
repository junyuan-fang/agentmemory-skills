#!/usr/bin/env python3
"""
Maintain a continuously-updated user profile (Honcho-lite).

Reads the last N days of conversations from sessions.db, prompts Claude
to merge new observations into the existing data/user-profile.md.

The profile captures: preferences, communication style, recurring tasks,
known facts about the user. Designed to be injected into Claude's system
prompt at session start so the agent "remembers" the user.

Usage:
    update-user-profile.py                    # use last 7 days
    update-user-profile.py --days 30
    update-user-profile.py --user "o9cq8"     # specific user only
    update-user-profile.py --reset            # rebuild from scratch
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from _claudecli import ensure_utf8_stdio, run_claude

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "sessions.db"
DEFAULT_PROFILE = REPO_ROOT / "data" / "user-profile.md"


PROMPT_TEMPLATE = """你是一个用户画像维护助手。你的任务是根据下面的【最近对话记录】,
**增量更新**【现有画像】,产出一份新的用户画像 markdown。

要求:
- 用第三人称写,称呼用户为"用户"
- 包含小节: 偏好风格、技术栈与角色、近期项目、沟通习惯、已知事实、注意事项
- 每一条最多一行,精炼
- 已有信息不要丢,除非新对话明确否定它
- 不要写"未知"、"不确定"、"基于推测"这种水分
- 不要复述对话内容,只提炼**长期有效**的信息
- 输出**纯 markdown**,不要加 JSON 包装,不要 ``` 包裹

=== 现有画像 ===
{existing}
=== 结束 ===

=== 最近对话 (按时间顺序) ===
{transcript}
=== 结束 ===

直接输出新的画像 markdown:
"""

EMPTY_PROFILE = """# 用户画像

## 偏好风格
- (尚无观察)

## 技术栈与角色
- (尚无观察)

## 近期项目
- (尚无观察)

## 沟通习惯
- (尚无观察)

## 已知事实
- (尚无观察)

## 注意事项
- (尚无观察)
"""


def gather(conn, days: int, user_filter: str | None) -> list:
    since = (dt.datetime.now() - dt.timedelta(days=days)).isoformat()
    where = ["timestamp >= ?"]
    params = [since]
    if user_filter:
        where.append("user_key LIKE ?")
        params.append(f"%{user_filter}%")
    sql = ("SELECT timestamp, role, content, user_name, user_key FROM turns "
           f"WHERE {' AND '.join(where)} ORDER BY timestamp")
    return conn.execute(sql, params).fetchall()


def all_users(conn, days: int) -> list[str]:
    since = (dt.datetime.now() - dt.timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT DISTINCT user_key FROM turns WHERE timestamp >= ? AND user_key != '' "
        "ORDER BY user_key", (since,)).fetchall()
    return [r[0] for r in rows]


def safe_filename(user_key: str) -> str:
    """user_key is any stable per-person id, e.g. 'alice@chat'. Convert to filesystem-safe name."""
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", user_key).strip("_")[:80]


def call_claude(prompt: str) -> str:
    return run_claude(prompt, timeout=300).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE,
                    help="path for the merged-all-users profile (default mode)")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--user", help="user_key substring filter")
    ap.add_argument("--per-user", action="store_true",
                    help="generate one profile per user under data/profiles/<user>.md "
                         "(in addition to the merged one)")
    ap.add_argument("--reset", action="store_true",
                    help="discard existing profile, build from scratch")
    ap.add_argument("--dry-run", action="store_true",
                    help="print prompt instead of calling claude")
    ap.add_argument("--commit", action="store_true",
                    help="git commit + try git push if profile files changed")
    args = ap.parse_args()
    ensure_utf8_stdio()

    if not args.db.exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    # 1. merged profile (existing behavior)
    args.profile.parent.mkdir(parents=True, exist_ok=True)
    existing = (EMPTY_PROFILE if args.reset or not args.profile.exists()
                else args.profile.read_text(encoding="utf-8"))

    rows = gather(conn, args.days, args.user)
    if not rows:
        print(f"(no turns in last {args.days} days)")
    else:
        print(f"  [merged] using {len(rows)} turns from last {args.days} day(s)…")
        transcript = render_transcript(rows)
        prompt = PROMPT_TEMPLATE.format(existing=existing, transcript=transcript)
        if args.dry_run:
            print(prompt); return 0
        new = call_claude(prompt)
        if new:
            new = re.sub(r"^```(?:markdown|md)?\s*", "", new)
            new = re.sub(r"\s*```\s*$", "", new)
            backup = args.profile.with_suffix(".md.bak")
            if args.profile.exists():
                backup.write_text(args.profile.read_text(encoding="utf-8"),
                                  encoding="utf-8")
            args.profile.write_text(new + "\n", encoding="utf-8")
            print(f"  + updated {args.profile.relative_to(REPO_ROOT)}")

    # 2. per-user profiles (new feature)
    if args.per_user:
        profiles_dir = args.profile.parent / "profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        users = all_users(conn, args.days)
        print(f"\n  [per-user] {len(users)} user(s) in last {args.days} day(s):")
        for uk in users:
            fname = safe_filename(uk) + ".md"
            fpath = profiles_dir / fname
            existing_u = (EMPTY_PROFILE if args.reset or not fpath.exists()
                          else fpath.read_text(encoding="utf-8"))
            urows = gather(conn, args.days, uk)
            if not urows: continue
            transcript = render_transcript(urows)
            prompt = PROMPT_TEMPLATE.format(existing=existing_u, transcript=transcript)
            new = call_claude(prompt)
            if not new: continue
            new = re.sub(r"^```(?:markdown|md)?\s*", "", new)
            new = re.sub(r"\s*```\s*$", "", new)
            header = f"<!-- user_key: {uk} ({len(urows)} turns) -->\n"
            fpath.write_text(header + new + "\n", encoding="utf-8")
            print(f"    + {fpath.relative_to(REPO_ROOT)}  ({len(urows)} turns)")

    if args.commit:
        try:
            subprocess.run(["git", "-C", str(REPO_ROOT), "add", "-A",
                            "data/user-profile.md",
                            "data/profiles/"],
                           capture_output=True)
            r = subprocess.run(["git", "-C", str(REPO_ROOT), "diff",
                                "--cached", "--quiet"], capture_output=True)
            if r.returncode != 0:
                subprocess.run(
                    ["git", "-C", str(REPO_ROOT), "commit", "-m",
                     f"profile: auto refresh {dt.datetime.now():%Y-%m-%d}"],
                    capture_output=True, check=True,
                )
                push = subprocess.run(
                    ["git", "-C", str(REPO_ROOT), "push"],
                    capture_output=True, timeout=60,
                )
                if push.returncode == 0:
                    print("  ✓ committed + pushed")
                else:
                    print("  ✓ committed; push failed (will retry next time)")
            else:
                print("  no profile changes to commit")
        except Exception as e:
            print(f"  commit step error: {e}", file=sys.stderr)

    return 0


def render_transcript(rows) -> str:
    transcript = "\n\n".join(
        f"[{r['timestamp'][:19]}] {r['role']} ({r['user_name'] or '-'}): "
        f"{r['content']}"
        for r in rows
    )
    if len(transcript) > 60000:
        transcript = transcript[-60000:]
    return transcript


if __name__ == "__main__":
    sys.exit(main())
