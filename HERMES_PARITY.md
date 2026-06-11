# Hermes 能力对照 —— 实现说明

逐条对照 Nous Research [hermes-agent](https://github.com/nousresearch/hermes-agent) 的关键能力,讲每条的**实现思路**和**代码位置**。还没做 / 故意不做的能力见 [ROADMAP.md](ROADMAP.md)。

## 总体设计

- **不碰 Claude Code** —— 只读它自己写的 transcript(`~/.claude/projects/**/*.jsonl`)做事后加工,零侵入
- **LLM 任务用 `claude -p` 子进程** —— 走你已有的 Claude Code 凭证,不管理 API key、不另计费
- **数据存 SQLite + markdown** —— 纯文件系统,易迁移、易备份、易 grep
- **cron 驱动,不跑 daemon** —— 单点失败少,调试简单

---

## #1 自演化技能(Self-improving Skill Loop)

| Hermes | 本项目 |
|---|---|
| Agent 完成任务后主动判定「这是新技能」并存档 | 三种触发提炼可复用 skill:关闭即沉淀 hook / cron / 主动 `/skill-extract` |
| 技能越用越精 | 同 slug 检测 → LLM 把旧 SKILL.md + 新对话**合并**成 v2/v3 |
| 兼容 agentskills.io 开放标准 | SKILL.md = YAML frontmatter + body,兼容 Claude Code 原生 skill 发现 |

**代码**:`scripts/extract-skill.py`
- `gather_turns()` —— 从 SQLite 拉指定时段 / session / FTS 查询的对话
- `call_claude()` —— `claude -p` 子进程调用
- `parse_skills()` —— 解析 LLM 返回的 JSON 数组
- `write_skill()` —— **核心**:同 slug 已存在 → 走 `MERGE_PROMPT` 让 LLM 增量合并(保旧吸新),递增 `version:` 字段
- 写完自动 `git commit` + `git push`(网络通时)

**三种沉淀触发**(详见 [`hooks/README.md`](hooks/README.md)):
1. **关闭即沉淀(被动)**:`hooks/distill-on-end.sh` 挂 Claude Code `SessionEnd` hook,关闭会话时对刚结束的 session 跑 index + extract
2. **定时沉淀**:cron 每天 03:30 扫昨天对话
3. **主动沉淀**:会话里发 `/skill-extract`(`ccskill extract`)

技能落到 `skills/<slug>/SKILL.md`。

## #2 长期记忆 & FTS5 全文检索

| Hermes | 本项目 |
|---|---|
| FTS5 索引所有会话 | 一致 —— SQLite + FTS5 `unicode61 remove_diacritics 2` |
| LLM 摘要历史 | `query-history.py --summary` 把检索结果喂回 `claude -p` |
| 跨 session 召回 | FTS 不限 session,按时间排 |
| 增量索引 | `INSERT OR IGNORE` + UNIQUE(project, session_id, timestamp, role) |

**代码**:`scripts/index-sessions.py`(建 / 增量更新)、`scripts/query-history.py`(检索,支持 `--since/--until/--user/--session/--role/--project/--summary`)

**调用**:`ccskill recall <kw> [--summary]`;IM 里 `/recall`。DB 在 `data/sessions.db`(gitignored)。

## #3 跨平台对话连续性

| Hermes | 本项目 |
|---|---|
| 在 Telegram 说「继续昨天那个项目」,Slack 也认得 | identity 映射 + 调用 `/cross-context` 注入其他平台上下文 |

**代码**:`scripts/cross-platform-context.py` + `data/identities.json`(真人 → 该人所有平台 user_key)

**调用**:
1. **被动**:用户提到「另一边怎么说过…」,Claude 调 `cross-platform-context.py --user-key XXX`
2. **主动**(可选):配 Claude Code SessionStart hook 自动跑

**当前限制**:默认按需调用(自动注入需自配 hook);identity 映射需手动在 `identities.json` 里维护。参考 `data/identities.example.json`。

## #4 用户建模(Honcho-lite)

| Hermes | 本项目 |
|---|---|
| 持续构建用户偏好 / 性格模型 | 每天 LLM 总结近 N 天对话,增量更新 `user-profile.md` |
| 跨 session 生效 | 通过项目级 `CLAUDE.md` 用 `@.../data/user-profile.md` 注入 |
| Honcho dialectic 辩证式建模 | **未做**,只做单次 LLM 摘要(见 ROADMAP) |

**代码**:`scripts/update-user-profile.py`
- 默认产出合并画像(所有用户)
- `--per-user`:每个 user_key 单独一份在 `data/profiles/<safe_key>.md`

**调用**:`ccskill profile --update`,或 cron 每天 04:00。

## #5 对话归档

每天把对话导出成人类可读 markdown(`data/archive/<date>.md`),便于离线翻阅 / 二次加工。

**代码**:`scripts/archive-session.py`。**调用**:`ccskill archive --date <d>`。

---

## 自动化:cron 计划表

```cron
0 * * * *  index-sessions.py                    # 每小时增量索引
10 3 * * * archive-session.py --date yesterday  # 03:10 归档昨天
30 3 * * * extract-skill.py --date yesterday    # 03:30 提炼新技能(含合并)
0 4 * * *  update-user-profile.py --per-user    # 04:00 刷新画像
50 4 * * * daily-sync.sh                         # 04:50 兜底 git 同步
```

完整可粘贴版本见 `cron/crontab.example`。

## 数据流总览

```
你用 Claude Code 聊天
   │
   ▼
Claude Code
   │ 读 CLAUDE.md → @-include 当前 user-profile.md(画像注入)
   │ 自动写 transcript → ~/.claude/projects/**/*.jsonl
   │
   ├──→ Claude 回复 → 你
   │
   └──→ (每小时) index → SQLite FTS5
        (每天)  archive / extract-skill / update-profile
        (按需)  cross-platform-context
```

## 已知取舍

- **计费**:所有 LLM 调用走 `claude -p` = 你的 Claude 订阅。cron 一天约 4–10 次调用,无额外 API 费。
- **同步**:写技能 / 画像后自动 commit,push 失败不阻断;`daily-sync.sh` 兜底补推。
- **重复检测粗糙**:仅同 slug 才合并,近似主题但不同 slug 不触发(可改进:embedding 相似度,见 ROADMAP)。
