#!/usr/bin/env python3
"""
Idempotently install (or remove) the SessionEnd "distill" hook in Claude Code's
settings.json. Safe to run repeatedly — backs up the file and never clobbers
your other settings or hooks.

Usage:
    install_hook.py --command "/abs/path/to/hooks/distill-on-end.sh"
    install_hook.py --command "..." --settings ~/.claude/settings.json
    install_hook.py --remove --command "..."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _claudecli import ensure_utf8_stdio

DEFAULT_SETTINGS = Path("~/.claude/settings.json").expanduser()


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        txt = path.read_text(encoding="utf-8").strip()
        return json.loads(txt) if txt else {}
    except json.JSONDecodeError as e:
        print(f"ERROR: {path} is not valid JSON ({e}). Fix it first.", file=sys.stderr)
        sys.exit(1)


def group_has_command(group: dict, command: str) -> bool:
    return any(h.get("command") == command for h in group.get("hooks", []) if isinstance(h, dict))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--command", required=True, help="absolute path to the hook script")
    ap.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    ap.add_argument("--event", default="SessionEnd")
    ap.add_argument("--remove", action="store_true", help="remove the hook instead of adding")
    args = ap.parse_args()
    ensure_utf8_stdio()

    settings = load(args.settings)
    hooks = settings.setdefault("hooks", {})
    events = hooks.setdefault(args.event, [])

    present = any(group_has_command(g, args.command) for g in events if isinstance(g, dict))

    if args.remove:
        if not present:
            print(f"  hook not present in {args.settings} — nothing to remove")
            return 0
        new_events = []
        for g in events:
            if isinstance(g, dict) and group_has_command(g, args.command):
                g["hooks"] = [h for h in g.get("hooks", [])
                              if not (isinstance(h, dict) and h.get("command") == args.command)]
                if g.get("hooks"):
                    new_events.append(g)
            else:
                new_events.append(g)
        hooks[args.event] = new_events
        action = "removed"
    else:
        if present:
            print(f"  hook already installed in {args.settings} — skipping (idempotent)")
            return 0
        events.append({"hooks": [{"type": "command", "command": args.command}]})
        action = "installed"

    args.settings.parent.mkdir(parents=True, exist_ok=True)
    if args.settings.exists():
        backup = args.settings.with_suffix(args.settings.suffix + ".bak")
        backup.write_text(args.settings.read_text(encoding="utf-8"), encoding="utf-8")
    args.settings.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print(f"  {action} {args.event} hook in {args.settings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
