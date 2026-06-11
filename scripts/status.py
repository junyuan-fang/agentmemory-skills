#!/usr/bin/env python3
"""
Self-check: is every part of agentmemory-skills actually installed & running?

Checks (cross-platform):
    1. SessionEnd hook registered in ~/.claude/settings.json
    2. Scheduled automation (Windows: Task Scheduler / else: crontab)
    3. Index database exists, turn count + freshest timestamp
    4. Skills dir (~/.claude/skills) and how many distilled skills
    5. Profile @import line in ~/.claude/CLAUDE.md
    6. Last distill activity in data/cron.log

Exit code 0 = all green; 1 = something missing (run install).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from _claudecli import ensure_utf8_stdio

REPO_ROOT = Path(__file__).resolve().parent.parent
DB = REPO_ROOT / "data" / "sessions.db"
LOG = REPO_ROOT / "data" / "cron.log"
SETTINGS = Path("~/.claude/settings.json").expanduser()
CLAUDE_MD = Path("~/.claude/CLAUDE.md").expanduser()
SKILLS_DIR = Path(
    os.environ.get("AGENTMEMORY_SKILLS_DIR", "~/.claude/skills")
).expanduser()

OK, BAD = "✓", "✗"


def check_hook() -> tuple[bool, str]:
    try:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return False, f"读不到 {SETTINGS}"
    for group in settings.get("hooks", {}).get("SessionEnd", []):
        for h in group.get("hooks", []) if isinstance(group, dict) else []:
            if "distill-on-end" in str(h.get("command", "")):
                return True, "SessionEnd hook 已注册(关闭会话即沉淀)"
    return False, "SessionEnd hook 未注册"


def check_scheduler() -> tuple[bool, str]:
    if os.name == "nt":
        r = subprocess.run(["schtasks", "/Query", "/TN", "AgentMemory-Index"],
                           capture_output=True)
        return (r.returncode == 0,
                "计划任务 AgentMemory-* 已注册" if r.returncode == 0
                else "计划任务未注册")
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode == 0 and "agentmemory-skills" in r.stdout:
        return True, "crontab 定时沉淀已配置"
    return False, "crontab 未配置"


def check_db() -> tuple[bool, str]:
    if not DB.exists():
        return False, "索引库不存在(跑 ccskill index)"
    try:
        conn = sqlite3.connect(DB)
        n = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        latest = conn.execute("SELECT MAX(timestamp) FROM turns").fetchone()[0]
        conn.close()
        return n > 0, f"索引库 {n} 条对话,最新 {str(latest)[:19]}"
    except sqlite3.Error as e:
        return False, f"索引库异常: {e}"


def check_skills() -> tuple[bool, str]:
    if not SKILLS_DIR.exists():
        return False, f"技能目录不存在: {SKILLS_DIR}"
    n = len(list(SKILLS_DIR.glob("*/SKILL.md")))
    return True, f"技能目录 {SKILLS_DIR}({n} 个技能)"


def check_profile_import() -> tuple[bool, str]:
    target = f"@{REPO_ROOT / 'data' / 'user-profile.md'}"
    try:
        if target in CLAUDE_MD.read_text(encoding="utf-8-sig"):
            return True, "画像 @import 已在 CLAUDE.md(每会话自动注入)"
    except FileNotFoundError:
        pass
    return False, "CLAUDE.md 没有画像 @import"


def check_distill_log() -> tuple[bool, str]:
    try:
        lines = [l for l in LOG.read_text(encoding="utf-8-sig").splitlines()
                 if l.startswith("[distill ")]
        if lines:
            return True, f"最近一次关闭即沉淀: {lines[-1][9:28]}"
    except FileNotFoundError:
        pass
    return True, "还没有关闭即沉淀的记录(退出一次 Claude 会话后再看)"


def main() -> int:
    ensure_utf8_stdio()
    # cc-connect 分支没有 hook / installer(纯 cron 驱动),相关检查不适用
    has_hook_support = (REPO_ROOT / "hooks").exists()
    checks = []
    if has_hook_support:
        checks.append(check_hook())
    checks += [check_scheduler(), check_db(), check_skills()]
    if has_hook_support:
        checks.append(check_profile_import())
        checks.append(check_distill_log())
    all_ok = True
    for ok, msg in checks:
        print(f"  {OK if ok else BAD} {msg}")
        all_ok = all_ok and ok
    if not all_ok:
        if has_hook_support:
            installer = "install.ps1" if os.name == "nt" else "./install.sh"
            print(f"\n有缺失 → 在仓库目录跑一次 {installer}(幂等,重复跑安全)")
        else:
            print("\n有缺失 → 参考 README 配置 crontab / 计划任务")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
