"""Cross-platform helpers shared by the ccskill scripts.

Why this exists: on Windows the `claude` command installed via npm is a
`.cmd` shim, which Python's subprocess (CreateProcess) cannot execute
directly — it must be routed through the shell. On Linux/macOS `claude` is a
normal executable and runs as-is. `shutil.which` resolves the right target
(respecting PATHEXT on Windows) so we don't depend on $PATH search semantics.
"""
from __future__ import annotations

import datetime as _dt
import os
import shutil
import subprocess
import sys


def ensure_utf8_stdio() -> None:
    """On Windows, force UTF-8 (errors→replace) on stdout/stderr.

    When output is piped or redirected (SessionEnd hook, Task Scheduler
    `>> log`, slash commands capturing output), Python defaults to the ANSI
    codepage (e.g. cp936), and characters like '⏎' or emoji raise
    UnicodeEncodeError. Interactive console output is unaffected.
    """
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_RELATIVE_DATES = {"today": 0, "今天": 0, "yesterday": 1, "昨天": 1, "前天": 2}


def resolve_date(s: str | None) -> str | None:
    """Resolve 'yesterday'/'昨天'/'today'/'今天'/'前天' to YYYY-MM-DD.

    Anything else passes through unchanged. Lets cron / Task Scheduler
    entries say `--date yesterday` instead of locale-dependent shell tricks
    (GNU `date -d` doesn't exist on macOS; `%DATE%` format varies by locale).
    """
    if not s:
        return s
    days = _RELATIVE_DATES.get(s.strip().lower())
    if days is None:
        return s
    return (_dt.date.today() - _dt.timedelta(days=days)).isoformat()


def claude_exe() -> str:
    """Resolve the claude CLI path, or fall back to the bare name."""
    return shutil.which("claude") or "claude"


def run_claude(prompt: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run `claude -p` cross-platform, feeding the prompt via stdin.

    The prompt must NOT go through argv: Windows caps a command line at
    ~32k chars (cmd.exe at ~8k) and our transcript prompts run to 50k+.
    Raises FileNotFoundError / subprocess.TimeoutExpired like subprocess.run
    does (callers handle them).
    """
    exe = claude_exe()
    args = [exe, "-p"]
    # A .cmd/.bat shim (typical for npm installs on Windows) needs the shell.
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        args = ["cmd", "/c", *args]
    return subprocess.run(args, input=prompt, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
