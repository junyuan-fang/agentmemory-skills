# 关闭即沉淀 —— SessionEnd hook

让 Claude Code **每次关闭会话时自动沉淀**:索引刚结束的 transcript + 提炼可复用技能。这是「被动沉淀」的主路径,不用你记得手动跑任何命令。

## 原理

Claude Code 在会话结束时会触发 `SessionEnd` hook,并通过 stdin 传入一个 JSON,含 `transcript_path`(刚结束会话的 `.jsonl`)和 `session_id`。`distill-on-end.sh`(Windows:`distill-on-end.ps1`,它把活交给 `distill-worker.ps1`)读到后:

1. `index-sessions.py --file <transcript>` —— 把这次会话增量索引进 `data/sessions.db`
2. `extract-skill.py --session <session_id>` —— 让 `claude -p` 从这次会话提炼 SKILL.md

整个动作**后台 detach** 执行,关 Claude 不会被卡住。

## 安装

把 `settings.snippet.json` 里的片段合并进你的 Claude Code `settings.json`
(用户级 `~/.claude/settings.json`,或项目级 `.claude/settings.json`),
并把 `command` 改成本仓库 `hooks/distill-on-end.sh` 的**绝对路径**:

```jsonc
{
  "hooks": {
    "SessionEnd": [
      { "hooks": [ { "type": "command",
        "command": "/home/you/code/agentmemory-skills/hooks/distill-on-end.sh" } ] }
    ]
  }
}
```

验证:开一个 Claude Code 会话、随便聊两句、退出,然后看
`data/cron.log` 是否多了一行 `[distill ...]`,以及 `ccskill recall` 能否检索到刚才的对话。

## 调参

- **觉得每次都 extract 太重 / 太慢**:把 `distill-on-end.sh`(Windows:`distill-worker.ps1`)里调用 `extract-skill.py` 那段注释掉。这样关闭时只做轻量索引,技能提炼交给每天的 cron / 计划任务(见 `../cron/crontab.example`)。
- **想连子 agent 的 transcript 一起沉淀**:给 `index-sessions.py` 加 `--include-sidechains`。

## Windows 注意

- 本目录的 `.ps1` 都带 UTF-8 **BOM**,改动后请保持(Windows PowerShell 5.1 把无 BOM 的 UTF-8 当 ANSI 解析,中文注释会直接引发语法错误)。
- 日志同样写到 `data/cron.log`(UTF-8),验证方法同上。

## 三种沉淀触发的关系

| 触发 | 谁来跑 | 何时 |
|---|---|---|
| 关闭即沉淀(被动) | 本 hook | 每次会话结束 |
| 定时沉淀 | cron | 每小时索引 / 每天提炼 + 画像 |
| 主动沉淀 | `/skill-extract` | 你在会话里随时手动触发 |

三者写的是同一个 `data/sessions.db` 和 `~/.claude/skills/`(Claude Code 全局技能目录,新会话自动读取),互不冲突(`INSERT OR IGNORE` 去重,同 slug 技能自动合并升版本)。
