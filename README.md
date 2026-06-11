# agentmemory-skills

> 用 Agent Skills 打造你自己的 Claude Code 版 Hermes —— 不烧 API,只用你已经充值的 Claude 订阅。

[Nous Research 的 Hermes](https://github.com/nousresearch/hermes-agent) 很强:长期记忆、自演化技能、跨平台对话连续性、用户建模。但它**每次都走 Claude API,按 token 另算钱**——你订阅 Claude 花的钱白花了,还要再为同一个模型付一遍。

这个项目用 **Agent Skills + `claude -p` 子进程**复刻了 Hermes 的核心能力,**全程复用你已有的 Claude Code 订阅,不消耗任何额外 API 额度**。适合已经充了 Claude、不想为「记忆 / 技能 / 画像」再单独烧 API 的朋友。

配合 [cc-connect](https://github.com/) 这类「本地 Claude Code × IM 桥」使用,你能直接在微信 / 飞书 / Telegram 里拥有一个**会记忆、会自我成长**的 Claude。

| | Hermes | 本项目 |
|---|---|---|
| LLM 调用 | Claude API,按 token 计费 | `claude -p` 子进程,复用 Claude 订阅,**$0 额外** |
| 记忆存储 | 托管服务 | 纯文件系统:SQLite + markdown,易备份易 grep |
| 部署 | serverless 平台 | 一台 Linux + cron,无 daemon |
| 数据归属 | 上云 | 全在你本地 |

---

## 核心能力:定时沉淀(Self-improving Loop)

最值钱的是这条**全自动的「沉淀」闭环**——你只管正常聊天,cron 每天把对话变成可复用的资产:

```
你在 IM 里正常和 Claude 聊天
        │
        ▼  cc-connect 把会话写成 JSON
   ~/.cc-connect/sessions/*.json
        │
        ├─(每小时) index-sessions.py   → SQLite FTS5 全文索引
        ├─(每天)  archive-session.py   → data/archive/<date>.md 人类可读归档
        ├─(每天)  extract-skill.py     → 扫昨天对话,LLM 提炼可复用 SKILL.md
        │                                同名技能自动「合并」升 v2/v3,越用越精
        └─(每天)  update-user-profile  → 增量更新用户画像,下次自动注入
```

聊三个月后,你会积累一批**只属于你**的工作习惯快捷动作 + 一份越来越懂你的画像——而这一切不需要你手动维护。

---

## 五大能力一览

| # | 能力 | 脚本 | 一句话 |
|---|---|---|---|
| 1 | 自演化技能 | `extract-skill.py` | 对话 → LLM 提炼 SKILL.md,同名合并升版本 |
| 2 | 长期记忆 + FTS5 检索 | `index-sessions.py` / `query-history.py` | 「上周那个 bug 怎么解决的」秒召回 + LLM 摘要 |
| 3 | 跨平台对话连续性 | `cross-platform-context.py` | 微信说过的话,飞书 / Telegram 也认得 |
| 4 | 用户建模(Honcho-lite) | `update-user-profile.py` | 持续构建偏好 / 风格画像,session 启动时注入 |
| 5 | 对话归档 | `archive-session.py` | 每天导出人类可读 markdown 备份 |

能力对 Hermes 的逐条实现对照见 [HERMES_PARITY.md](HERMES_PARITY.md);**还没做 / 故意不做**的能力见 [ROADMAP.md](ROADMAP.md)。

---

## 快速开始

前置:Python 3、[Claude Code](https://claude.com/claude-code) CLI(`claude` 在 PATH 里)、一个会把对话写成 JSON 的 IM 桥(如 cc-connect)。

```bash
git clone https://github.com/junyuan-fang/agentmemory-skills.git
cd agentmemory-skills

# 1. 把 ccskill 软链进 PATH
ln -s "$PWD/scripts/ccskill" ~/.local/bin/ccskill

# 2. 首次建立全文索引(默认读 ~/.cc-connect/sessions/)
ccskill index

# 3. 试试检索
ccskill recall "关键词"
ccskill recall "关键词" --summary      # + LLM 摘要

# 4. 从昨天的对话提炼技能(沉淀到 ~/.claude/skills/<slug>/,全局 Claude 新会话自动读取)
ccskill extract --date yesterday      # 也支持 昨天/today/今天 或 YYYY-MM-DD

# 5. 刷新用户画像
ccskill profile --update
```

会话目录不是默认路径时,给脚本传 `--sessions-dir` 或设环境变量 `AGENTMEMORY_SESSIONS_DIR`;`AGENTMEMORY_REPO` 可指定本仓库位置。Windows 上把 `scripts` 目录加进 PATH,用 `ccskill.cmd`(用法相同)。

### 全自动化(cron)

把 [`cron/crontab.example`](cron/crontab.example) 里的几行按你的绝对路径改好,`crontab -e` 粘进去即可。一天约 4–10 次 `claude -p` 调用(复用订阅,无额外 API 费)。

---

## `ccskill` 命令

```
ccskill recall <kw> [--summary]   FTS 检索历史(可选 LLM 摘要)
ccskill index                     重建 / 增量索引
ccskill extract --date <d>        从对话提炼技能
ccskill profile [--update]        查看 / 刷新用户画像
ccskill context --person <name>   注入某人其他平台的近期上下文
ccskill archive --date <d>        导出某天对话为 markdown
ccskill list                      列出已提炼的技能
ccskill show <slug>               查看某个技能
ccskill sync                      git pull + push
```

在 IM 里,通过把 [`commands/`](commands/) 下的 slash command 定义放进 `~/.claude/commands/`,可直接发 `/recall`、`/skill-extract`、`/profile`、`/cross-context`。

---

## 设计原则

- **不改 IM 桥源码** —— 只对它产出的 session JSON 做「事后加工」,零 fork 维护成本
- **LLM 任务一律 `claude -p`** —— 走你已有的 Claude Code 凭证,不管理 API key、不另计费
- **纯文件系统** —— SQLite + markdown,易迁移、易备份、易 grep,数据全在本地
- **cron 驱动,不跑 daemon** —— 单点失败少,调试简单

## 隐私

本仓库**只含代码**。所有个人数据(`data/sessions.db`、`data/archive/`、`data/profiles/`、真实 `identities.json`、`user-profile.md`)都被 `.gitignore` 排除,不会进版本库。

## 迁移到其他 agent

设计跟 Claude Code / cc-connect 耦合很松:把 `index-sessions.py` 改成读你 agent 的对话格式、把 `claude -p` 换成别的 CLI 即可。`SKILL.md` 是 `name/description/body` 的开放格式,兼容 [agentskills.io](https://agentskills.io)。

## License

[Apache License 2.0](LICENSE)
