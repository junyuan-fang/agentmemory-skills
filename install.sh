#!/usr/bin/env bash
# agentmemory-skills 一键安装(Linux / macOS / WSL / Git Bash)。
# 装完即全自动:关闭会话自动沉淀 + 每日 cron 沉淀 + 斜杠命令可用。
# 幂等:重复跑安全。卸载:./install.sh --uninstall
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)"
PY="$(command -v python3 || command -v python || true)"
CCSKILL="$REPO/scripts/ccskill"
HOOK="$REPO/hooks/distill-on-end.sh"
BINDIR="$HOME/.local/bin"
CMDDIR="$HOME/.claude/commands"
CRON_BEGIN="# >>> agentmemory-skills >>>"
CRON_END="# <<< agentmemory-skills <<<"

uninstall() {
  echo "卸载 agentmemory-skills…"
  [ -L "$BINDIR/ccskill" ] && rm -f "$BINDIR/ccskill" && echo "  - 移除 $BINDIR/ccskill"
  [ -L "$BINDIR/kskill" ] && rm -f "$BINDIR/kskill" && echo "  - 移除 $BINDIR/kskill(旧名遗留)"
  if [ -n "$PY" ]; then "$PY" "$REPO/scripts/install_hook.py" --remove --command "$HOOK" || true; fi
  if crontab -l >/dev/null 2>&1; then
    crontab -l 2>/dev/null | sed "/$CRON_BEGIN/,/$CRON_END/d" | crontab - || true
    echo "  - 移除 cron 计划"
  fi
  # 移除 CLAUDE.md 里的画像 import(沉淀在 ~/.claude/skills 的技能保留,属于你的数据)
  CLAUDE_MD="$HOME/.claude/CLAUDE.md"
  if [ -f "$CLAUDE_MD" ]; then
    grep -vxF "@$REPO/data/user-profile.md" "$CLAUDE_MD" \
      | grep -vxF "# agentmemory-skills: 用户画像自动注入" > "$CLAUDE_MD.tmp" || true
    mv "$CLAUDE_MD.tmp" "$CLAUDE_MD"
    echo "  - 移除 CLAUDE.md 画像 import"
  fi
  echo "完成(斜杠命令文件 $CMDDIR 下的保留,可自行删除)。"
  exit 0
}

[ "${1:-}" = "--uninstall" ] && uninstall
[ -z "$PY" ] && { echo "找不到 python3,请先装 Python 3。"; exit 1; }

echo "==> 安装 agentmemory-skills (repo: $REPO)"

# 1) ccskill 软链进 PATH(顺手清掉旧名 kskill 的遗留软链)
mkdir -p "$BINDIR"
ln -sf "$CCSKILL" "$BINDIR/ccskill"
[ -L "$BINDIR/kskill" ] && rm -f "$BINDIR/kskill"
echo "  ✓ ccskill → $BINDIR/ccskill"
case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) echo "  ⚠ $BINDIR 不在 PATH 里,请在 ~/.bashrc / ~/.zshrc 加: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# 2) 斜杠命令
mkdir -p "$CMDDIR"
cp "$REPO"/commands/*.md "$CMDDIR"/ 2>/dev/null || true
echo "  ✓ 斜杠命令 → $CMDDIR ( /recall /skill-extract /profile /cross-context )"

# 3) SessionEnd hook(关闭即沉淀)
chmod +x "$HOOK" 2>/dev/null || true
"$PY" "$REPO/scripts/install_hook.py" --command "$HOOK"

# 4) 首次建立索引
echo "  … 索引已有的 Claude Code 会话(首次可能要几秒)"
"$PY" "$REPO/scripts/index-sessions.py" >/dev/null 2>&1 || echo "  ⚠ 索引失败(可能还没有 Claude Code 会话,稍后 ccskill index 重试)"
echo "  ✓ 索引完成"

# 5) cron 定时沉淀(自包含 PATH,免去全局 PATH= 冲突)
CLAUDE_BIN="$(command -v claude || true)"
CLAUDE_DIR="$([ -n "$CLAUDE_BIN" ] && dirname "$CLAUDE_BIN" || echo "$HOME/.local/bin")"
PY_DIR="$(dirname "$PY")"
CRON_PATH="$CLAUDE_DIR:$PY_DIR:/usr/local/bin:/usr/bin:/bin"
LOG="$REPO/data/cron.log"
NEWBLOCK="$(cat <<EOF
$CRON_BEGIN
0 * * * * PATH="$CRON_PATH" "$PY" "$REPO/scripts/index-sessions.py" >> "$LOG" 2>&1
10 3 * * * PATH="$CRON_PATH" "$PY" "$REPO/scripts/archive-session.py" --date yesterday >> "$LOG" 2>&1
30 3 * * * PATH="$CRON_PATH" "$PY" "$REPO/scripts/extract-skill.py" --date yesterday >> "$LOG" 2>&1
0 4 * * * PATH="$CRON_PATH" "$PY" "$REPO/scripts/update-user-profile.py" --days 7 --per-user >> "$LOG" 2>&1
$CRON_END
EOF
)"
if command -v crontab >/dev/null 2>&1; then
  ( crontab -l 2>/dev/null | sed "/$CRON_BEGIN/,/$CRON_END/d"; echo "$NEWBLOCK" ) | crontab -
  echo "  ✓ cron 定时沉淀已装(每小时索引 / 每天 03:30 提炼 / 04:00 画像)"
else
  echo "  ⚠ 没有 crontab(WSL 可 'sudo service cron start';或忽略,关闭即沉淀已够用)"
fi

# 6) 画像自动注入:往全局 CLAUDE.md 加一行 @import,每个新会话自动带上画像
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
PROFILE_MD="$REPO/data/user-profile.md"
[ -f "$PROFILE_MD" ] || printf '# 用户画像\n\n(尚未生成 — 跑 ccskill profile --update)\n' > "$PROFILE_MD"
IMPORT="@$PROFILE_MD"
mkdir -p "$(dirname "$CLAUDE_MD")"
if ! grep -qxF "$IMPORT" "$CLAUDE_MD" 2>/dev/null; then
  printf '\n# agentmemory-skills: 用户画像自动注入\n%s\n' "$IMPORT" >> "$CLAUDE_MD"
  echo "  ✓ 画像 import → $CLAUDE_MD"
else
  echo "  ✓ 画像 import 已在 CLAUDE.md"
fi

cat <<EOF

✅ 装好了,之后全自动,无需任何手动操作:
   · 关闭 Claude 会话  → 自动索引 + 提炼技能(SessionEnd hook)
   · 每天后台          → 提炼技能 + 刷新画像(cron)
   · 随时手动          → ccskill recall / extract / profile,或对话里 /recall

试一下:  ccskill recall "你聊过的某个话题"
卸载:    $REPO/install.sh --uninstall
EOF
