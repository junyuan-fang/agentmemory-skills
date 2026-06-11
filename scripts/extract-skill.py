#!/usr/bin/env python3
"""
LLM-driven skill extraction: feed a slice of session history to Claude
and ask it to distill any **reusable workflows** into Claude Code skill
files (the SKILL.md format).

Usage:
    extract-skill.py --session s1            # extract from one session
    extract-skill.py --date 2026-05-14       # all turns from a date
    extract-skill.py --since 2026-05-10      # since a date
    extract-skill.py --query "deploy setup" # turns matching FTS query
    extract-skill.py --dry-run               # print the prompt, don't call claude

What it does:
    1. Pull matching turns from sessions.db
    2. Prompt Claude (via local CLI) to identify "this is something the user
       did more than once / would do again", and write a SKILL.md for each
    3. Save each skill to ~/.claude/skills/<slug>/SKILL.md — Claude Code's
       global skills dir, so every new session auto-discovers them.
       Override with AGENTMEMORY_SKILLS_DIR (e.g. point it back inside the
       repo if you want skills version-controlled).
    4. git-commit + push, only when the skills dir lives inside this repo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from _claudecli import ensure_utf8_stdio, resolve_date, run_claude

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root
DEFAULT_DB = REPO_ROOT / "data" / "sessions.db"
# 默认沉淀进 Claude Code 的全局技能目录,新会话自动读取
SKILLS_DIR = Path(
    os.environ.get("AGENTMEMORY_SKILLS_DIR", "~/.claude/skills")
).expanduser()


PROMPT_TEMPLATE = """你是一个 skill 提炼助手。下面是用户最近的若干轮对话历史(role=user 是用户的请求, role=assistant 是 AI 助手 Claude 的回复)。

请仔细阅读,识别出**所有"用户多次做、或者将来会反复用到"的具体工作流/技巧**,然后为每个这样的工作流生成一份 Claude Code 风格的 SKILL.md 文件。

判定标准(都满足才算):
- 是一个**完整可复现**的小流程(不是知识陈述)
- **超过 3 行**的操作步骤,或包含**特定命令/参数/路径**
- 用户给出过明确的"以后这样做"或类似确认,**或**这个操作 解决了一个实际问题

不要生成的内容:
- 笼统的最佳实践、纯讲解、原理说明
- 一次性配置(写完就不再用的)
- AI 自己提议但用户没采纳的

输出格式(严格遵守, JSON list, 每个对象一个 skill):

```json
[
  {{
    "slug": "kebab-case-name",
    "title": "短标题(中文也行)",
    "description": "一句话描述: 什么时候用这个 skill",
    "trigger_keywords": ["关键词1", "关键词2"],
    "body": "## 步骤\\n\\n1. ...\\n2. ...\\n\\n## 注意\\n\\n..."
  }}
]
```

如果没有任何值得提炼的工作流,直接输出 `[]`。

不要输出任何解释、寒暄、markdown 块外的文字。只输出 JSON。

=== 对话历史 ===
{transcript}
=== 结束 ===
"""


def gather_turns(conn: sqlite3.Connection, args) -> list[sqlite3.Row]:
    where, params = [], []
    if args.session:
        where.append("session_id = ?"); params.append(args.session)
    if args.date:
        where.append("substr(timestamp,1,10) = ?"); params.append(args.date)
    if args.since:
        where.append("timestamp >= ?"); params.append(args.since)
    if args.until:
        where.append("timestamp < ?"); params.append(args.until)

    if args.query:
        tokens = re.findall(r"\S+", args.query)
        fts = " ".join('"' + t.replace('"', '""') + '"' for t in tokens)
        sql = ("SELECT t.* FROM turns t JOIN turns_fts f ON f.rowid=t.id "
               "WHERE turns_fts MATCH ?")
        params = [fts] + params
    else:
        sql = "SELECT * FROM turns WHERE 1=1"

    if where:
        sql += " AND " + " AND ".join(where)
    sql += " ORDER BY timestamp"
    return conn.execute(sql, params).fetchall()


def render_transcript(rows) -> str:
    lines = []
    for r in rows:
        ts = r["timestamp"][:19]
        lines.append(f"[{ts}] {r['role']}: {r['content']}")
    return "\n\n".join(lines)


def call_claude(prompt: str) -> str:
    try:
        return run_claude(prompt, timeout=300).stdout
    except FileNotFoundError:
        print("ERROR: claude CLI not found", file=sys.stderr)
        sys.exit(2)
    except subprocess.TimeoutExpired:
        print("ERROR: claude timeout", file=sys.stderr)
        sys.exit(2)


def parse_skills(output: str) -> list[dict]:
    # find first [ ... ] block; tolerate wrappers
    m = re.search(r"\[\s*(?:\{.*?\}\s*,?\s*)*\]", output, re.DOTALL)
    if not m:
        # try a fenced json block
        m2 = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", output, re.DOTALL)
        raw = m2.group(1) if m2 else output
    else:
        raw = m.group(0)
    try:
        skills = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"WARN: failed to parse skills JSON: {e}", file=sys.stderr)
        print("--- raw output ---", file=sys.stderr)
        print(output[:2000], file=sys.stderr)
        return []
    if not isinstance(skills, list):
        return []
    return skills


def slugify(s: str) -> str:
    """ASCII kebab-case — Claude Code 只认 [a-z0-9-] 的技能名。"""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")[:64]
    if not slug:
        # 纯中文标题 → 稳定短 hash,同名技能下次仍能合并升版
        slug = "skill-" + hashlib.md5(s.encode("utf-8")).hexdigest()[:8]
    return slug


MERGE_PROMPT = """已有一个 SKILL.md, 现在又从新的对话里提炼出关于**同一主题**的更新版本。请把两者合并成一个更完善的 SKILL.md。

要求:
- **保留旧版的有效信息**, 除非新对话明确否定它
- **吸收新版的补充和修正**
- 不要重复, 不要删减步骤变成更模糊的版本
- 步骤、命令、路径要具体
- 输出**完整 markdown**, 不要 ``` 包裹, 不要解释

=== 旧版 SKILL.md ===
{old}
=== 结束 ===

=== 新提炼的内容 (frontmatter 字段) ===
title: {title}
description: {desc}
keywords: {kws}
body:
{body}
=== 结束 ===

直接输出合并后的完整 SKILL.md (包括 frontmatter):
"""


def _frontmatter_str(slug, desc, kws, source_label, version):
    return (f"---\nname: {slug}\n"
            f"description: {desc}\n"
            f"trigger_keywords: [{', '.join(json.dumps(k, ensure_ascii=False) for k in kws)}]\n"
            f"source: {source_label}\n"
            f"version: {version}\n"
            f"updated_at: {datetime.now().isoformat(timespec='seconds')}\n"
            f"---\n\n")


def write_skill(skill: dict, source_label: str) -> Path | None:
    slug = slugify(skill.get("slug") or skill.get("title") or "untitled")
    if not slug:
        return None
    skill_dir = SKILLS_DIR / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    title = skill.get("title", slug)
    desc = skill.get("description", "")
    kws = skill.get("trigger_keywords", []) or []
    body = skill.get("body", "")

    path = skill_dir / "SKILL.md"

    if path.exists():
        # SAME-SLUG MERGE: ask claude to combine old + new
        old = path.read_text(encoding="utf-8")
        prev_version = 1
        m = re.search(r"^version:\s*(\d+)", old, re.MULTILINE)
        if m:
            prev_version = int(m.group(1))
        new_version = prev_version + 1

        merge_prompt = MERGE_PROMPT.format(
            old=old, title=title, desc=desc, kws=kws, body=body,
        )
        merged = call_claude(merge_prompt).strip()
        merged = re.sub(r"^```(?:markdown|md)?\s*", "", merged)
        merged = re.sub(r"\s*```\s*$", "", merged)
        if not merged.startswith("---"):
            # fallback: rebuild frontmatter + use merged as body
            merged = _frontmatter_str(slug, desc, kws, source_label, new_version) + merged

        # ensure version is updated even if LLM forgot
        merged = re.sub(r"^version:\s*\d+",
                        f"version: {new_version}",
                        merged, count=1, flags=re.MULTILINE)
        if "version:" not in merged.split("---", 2)[1] if merged.startswith("---") else True:
            # no version field → inject
            merged = re.sub(r"(^---\n)",
                            f"\\1version: {new_version}\n", merged,
                            count=1, flags=re.MULTILINE)
        path.write_text(merged + ("\n" if not merged.endswith("\n") else ""),
                        encoding="utf-8")
        print(f"  ↻ merged into existing {slug}/SKILL.md (v{new_version})")
        return path

    # NEW SKILL
    md = (_frontmatter_str(slug, desc, kws, source_label, version=1)
          + f"# {title}\n\n{body.strip()}\n")
    path.write_text(md, encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    g = ap.add_argument_group("source filter (combinable)")
    g.add_argument("--session", help="session_id")
    g.add_argument("--date", help="YYYY-MM-DD, or yesterday/昨天/today/今天")
    g.add_argument("--since")
    g.add_argument("--until")
    g.add_argument("--query", help="FTS query")
    ap.add_argument("--dry-run", action="store_true",
                    help="only print the prompt, don't call claude")
    ap.add_argument("--no-commit", action="store_true",
                    help="skip git commit after writing skills")
    args = ap.parse_args()
    ensure_utf8_stdio()
    args.date = resolve_date(args.date)
    args.since = resolve_date(args.since)
    args.until = resolve_date(args.until)

    if not args.db.exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = gather_turns(conn, args)
    if not rows:
        print("(no turns match)")
        return 0
    print(f"  feeding {len(rows)} turns to claude…")

    transcript = render_transcript(rows)
    # cap transcript at ~50k chars to avoid context overflow
    if len(transcript) > 50000:
        transcript = transcript[-50000:]
        print(f"  (truncated to last 50k chars)")

    prompt = PROMPT_TEMPLATE.format(transcript=transcript)

    if args.dry_run:
        print(prompt)
        return 0

    raw = call_claude(prompt)
    skills = parse_skills(raw)
    if not skills:
        print("  (no skills extracted)")
        return 0

    src_label = (f"session={args.session}" if args.session else
                 f"date={args.date}" if args.date else
                 f"since={args.since}" if args.since else
                 f"query={args.query}" if args.query else "all")

    written = []
    for s in skills:
        p = write_skill(s, src_label)
        if p:
            print(f"  + {p}")
            written.append(p)

    # 技能目录在仓库内才有 commit 的意义(默认在 ~/.claude/skills,跳过)
    try:
        skills_in_repo = SKILLS_DIR.resolve().relative_to(REPO_ROOT.resolve()) is not None
    except ValueError:
        skills_in_repo = False

    if written and skills_in_repo and not args.no_commit:
        try:
            subprocess.run(["git", "-C", str(REPO_ROOT), "add", "-A"],
                           check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(REPO_ROOT), "commit", "-m",
                 f"skills: extract {len(written)} skill(s) from {src_label}"],
                check=True, capture_output=True,
            )
            print(f"  git committed.")
            push = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "push"],
                capture_output=True, timeout=60,
            )
            if push.returncode == 0:
                print(f"  ✓ pushed to remote")
            else:
                err = push.stderr.decode(errors="replace")[:200]
                print(f"  push failed (commit kept locally): {err.strip()}",
                      file=sys.stderr)
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode() if e.stderr else str(e)
            print(f"  git commit skipped: {err.strip()}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
