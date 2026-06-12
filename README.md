[English](README.en.md) | **简体中文**

# agentmemory-skills

**给 Claude Code 装上「长期记忆」和「自我成长」——而且不花一分额外的 API 钱。**

Claude Code 本身很强,但它有个毛病:**每次开新会话都像失忆**。上周怎么修的那个 bug、上个月帮你定的命名规范、你反复交代的偏好——关掉窗口就忘了。你只能一遍遍重新解释。

`agentmemory-skills` 解决这个问题。它在后台默默读 Claude Code 自己存的聊天记录,帮你:

- 🔍 **记住所有对话**,随时一句话搜回来(「上次那个部署脚本怎么写的?」)
- 🧠 **把反复出现的操作自动攒成「技能」**,越用越熟
- 👤 **慢慢学会你的偏好和工作方式**,下次主动用上
- 🔁 **跨设备/平台记得你**(配合 IM 桥时)

关键是:这一切的「思考」都用你**已经订阅的 Claude Code**(通过 `claude -p` 命令)完成,**不调用按量计费的 API,不额外花钱**。

> 灵感来自 [Nous Research 的 Hermes](https://github.com/nousresearch/hermes-agent)——但 Hermes 走 Claude API 按 token 收费,这个项目复用你的订阅,$0 额外成本。

---

## 一个例子,秒懂它干嘛

**没有它**:
```
你(新会话): 上次我们怎么解决那个 SQLite 锁的问题来着?
Claude:    我没有之前对话的记忆,你能描述一下吗?
你:        (叹气,开始重新解释……)
```

**有了它**:
```
$ ccskill recall "SQLite 锁"
[05-28 14:02] user   | 写并发的时候 database is locked 报错
[05-28 14:03] assist | 改成 WAL 模式:PRAGMA journal_mode=WAL,并设 busy_timeout…

$ ccskill recall "SQLite 锁" --summary
--- 摘要 ---
上次的结论:并发写 SQLite 用 WAL 模式 + busy_timeout=5000,
单写多读场景够用;真高并发再上 Postgres。
```

一句话搜回三周前的结论,不用翻聊天记录,也不用重新问 Claude。

---

## 你能用它做什么

装好后你会多出一个命令 `ccskill`(和几个可选的 `/斜杠命令`):

| 你想干嘛 | 命令 | 它做了什么 |
|---|---|---|
| 搜历史对话 | `ccskill recall "关键词"` | 全文检索所有 Claude Code 会话,毫秒级 |
| 搜 + 让 Claude 总结 | `ccskill recall "关键词" --summary` | 检索后把结果丢给 Claude 提炼要点 |
| 把对话攒成技能 | `ccskill extract --date 昨天` | 让 Claude 读对话,自动写出可复用的 `SKILL.md` |
| 看/刷新「它对你的画像」 | `ccskill profile --update` | 总结你的偏好、技术栈、习惯,存成 markdown |
| 列出攒下的技能 | `ccskill list` | 看你积累了哪些自动提炼的工作流 |
| 导出某天对话备份 | `ccskill archive --date 2026-06-01` | 存成人类可读的 markdown |

---

## 安装:一条命令,之后全自动

**前置**:你已经在用 [Claude Code](https://claude.com/claude-code) CLI(命令行能跑 `claude`)+ Python 3。就这两个。

### Linux / macOS / WSL / Git Bash

```bash
git clone https://github.com/junyuan-fang/agentmemory-skills.git
cd agentmemory-skills
./install.sh
```

### Windows(原生 PowerShell)

```powershell
git clone https://github.com/junyuan-fang/agentmemory-skills.git
cd agentmemory-skills
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

**就这样,装完不用再碰任何配置。** `install` 会自动帮你:

- ✅ 把 `ccskill` 命令装进 PATH(任意目录可用)
- ✅ 索引你已有的全部 Claude Code 会话
- ✅ 装好 **关闭会话即自动沉淀** 的 hook(写进 `~/.claude/settings.json`,自动备份、幂等)
- ✅ 装好 **每天定时沉淀** 的计划任务(Linux/mac 用 cron,Windows 用任务计划程序)
- ✅ 把 `/recall`、`/skill-extract`、`/profile` 等斜杠命令放进 `~/.claude/commands/`
- ✅ 技能沉淀进 `~/.claude/skills/`、画像 import 进 `~/.claude/CLAUDE.md` —— **全局 Claude 每个新会话自动读取**

之后你只管正常用 Claude Code,记忆和技能在后台自动沉淀。**新开一个终端**验证一下:

```bash
ccskill status                       # 自检:hook/计划任务/索引/画像注入 是否全就位
ccskill recall "你最近聊过的某个话题"   # 试试检索
```

> ⚠️ 只把仓库 clone 下来、零散跑过几个脚本 ≠ 装好了。自动沉淀(hook + 定时任务)
> 必须经 `install` 注册,怀疑没装就 `ccskill status`,有 ✗ 就再跑一次 install。

> 重复跑 `install` 是安全的(幂等)。要全部撤掉:`./install.sh --uninstall`(Windows:`install.ps1 -Uninstall`)。
> 嫌每次关会话都提炼太重?见 [`hooks/README.md`](hooks/README.md) 改成只索引。

---

## 三种沉淀,装完即生效

「沉淀」= 把对话变成记忆和技能。上面的 `install` 已经把下面三种触发**全部自动装好**,你不用做任何事:

| 触发 | 何时跑 | 谁装的 |
|---|---|---|
| **① 关闭即沉淀** | 每次你关掉 Claude 会话 → 自动索引 + 提炼刚才那次 | SessionEnd hook |
| **② 定时沉淀** | 每小时索引、每天 03:30 提炼技能、04:00 刷新画像 | cron / 任务计划程序 |
| **③ 主动沉淀** | 你在对话里随手发 `/skill-extract` 立即提炼 | 斜杠命令 |

三者写同一个数据库,互不冲突。日志在 `data/cron.log`,想确认在跑就 `tail -f data/cron.log`。

<details>
<summary>不想用 install 脚本?手动配置 / 自定义(点开)</summary>

- **只装命令**:`ln -s "$PWD/scripts/ccskill" ~/.local/bin/ccskill`(Windows 把 `scripts` 加进 PATH,用 `ccskill.cmd`),然后 `ccskill index`。
- **① 关闭即沉淀 hook**:把 [`hooks/distill-on-end.sh`](hooks/distill-on-end.sh)(Windows:`.ps1`)的绝对路径填进 `~/.claude/settings.json` 的 `hooks.SessionEnd`。细节见 [`hooks/README.md`](hooks/README.md)。
- **② 定时沉淀**:Linux/mac 参考 [`cron/crontab.example`](cron/crontab.example) 改路径后 `crontab -e`;Windows 用 `schtasks` 注册(install.ps1 里有现成写法)。
- **③ 斜杠命令**:把 [`commands/`](commands/) 下的 `.md` 拷进 `~/.claude/commands/`。
- 嫌每次关会话都提炼太重:把 `hooks/distill-on-end.*` 里调用 `extract-skill` 那行注释掉,只留索引,提炼交给每天的定时任务。

</details>

## 为什么不花额外的钱

很多类似工具(包括 Hermes)做「记忆/总结」时会调 Claude 的 **API**——那是**按 token 单独计费**的,你订阅 Claude 的钱不算数,得再充一份。

这个项目所有需要「让 AI 思考」的地方(总结、提炼技能、更新画像)都通过 `claude -p` 命令完成,**直接复用你已经登录的 Claude Code**。一天大约 4–10 次调用,全部走你的订阅额度,**API 账单为 $0**。

| | 走 API 的方案 | 本项目 |
|---|---|---|
| 每次 AI 调用 | 按 token 计费,另付钱 | 复用 Claude 订阅,$0 额外 |
| 数据存哪 | 多半上云 | 全在你本地(SQLite + markdown) |
| 依赖 | 云服务 / API key | 一台机器 + Claude Code,没了 |

---

## agentmemory-skills 对标 Hermes:都有什么

| 能力 | Hermes | 本项目 |
|---|:---:|:---:|
| 长期记忆 + 全文检索(FTS5) | ✅ | ✅ |
| 自演化技能(对话 → 技能,越用越精) | ✅ | ✅ |
| 自动沉淀(无需手动触发) | ✅ | ✅ hook + cron |
| 跨平台对话连续性 | ✅ | ✅ 需 identity 映射 |
| 用户建模 / 画像 | ✅ Honcho 辩证式 | ⚠️ 单次 LLM 摘要 |
| 隔离子 agent 并行 | ✅ | ❌ 故意不做 |
| Hibernate 按需唤醒降本 | ✅ | ❌ 不做 |
| 200+ 模型路由(OpenRouter) | ✅ | ❌ 会破坏省钱定位 |
| RL trajectory / Atropos | ✅ | ❌ |
| **每次 AI 调用计费** | 💸 走 API,按 token | ✅ **复用 Claude 订阅,$0 额外** |
| **数据 / 部署** | ☁️ 多半上云 | ✅ **全在本地,一台机器** |

一句话:**核心记忆能力打平,省钱和本地化我们赢,重型分布式能力(子 agent / 休眠 / 模型路由)是 Hermes 的强项、我们故意不碰。**

> 逐条实现细节见 [HERMES_PARITY.md](HERMES_PARITY.md);⚠️/❌ 的取舍与计划见 [ROADMAP.md](ROADMAP.md)。

---

## 它是怎么工作的

```
你正常用 Claude Code 聊天
        │
        ▼   Claude Code 自动把每次会话写成 transcript
   ~/.claude/projects/**/*.jsonl        ← 本项目唯一的数据来源(只读,不改)
        │
        ▼   sediment「沉淀」(hook / cron / 手动 触发)
   ┌──────────────┬────────────────┬─────────────────┐
   索引到 SQLite     提炼成 SKILL.md     更新用户画像        归档成 markdown
   (秒级全文搜)     (技能越用越精)     (下次自动注入)     (人类可读备份)
        │
        ▼
   你用 ccskill / 斜杠命令 把这些随时调出来
```

整套设计:**不碰 Claude Code 本体**(只读它的记录)、**纯文件系统**(SQLite + markdown,好备份好 grep)、**cron/hook 驱动**(没有常驻进程)。

---

## FAQ

**Q:它会读我所有 Claude Code 项目的对话吗?**

A:是的,默认索引 `~/.claude/projects/` 下全部。数据库 `data/sessions.db` 只在你本地,不上传任何地方。

---

**Q:会泄漏我的对话到 GitHub 吗?**

A:不会。所有个人数据(数据库、归档、画像、日志)都被 `.gitignore` 排除,这个仓库**只含代码**。

---

**Q:「提炼技能」具体是啥?**

A:Claude 读你的对话,识别出「这套操作你做过不止一次 / 以后还会用」,写成一份 `SKILL.md`(带步骤、命令)。同一主题再出现时,它会把新旧版本**合并升级**(v2、v3……),越用越完善。

技能直接沉淀到 **`~/.claude/skills/<slug>/`** —— 这是 Claude Code 的全局技能目录,**每个新会话自动发现并按需调用**,不用任何额外配置。想换地方(比如收进本仓库做版本管理)设环境变量 `AGENTMEMORY_SKILLS_DIR`。用户画像同理:install 会往 `~/.claude/CLAUDE.md` 加一行 `@import`,每个新会话自动带上画像。

---

**Q:需要 IM(微信 / 飞书 / Telegram)吗?**

A:不需要。`master` 分支直接读 Claude Code 命令行的记录。如果你是**经 IM 桥**用 Claude(比如 [cc-connect](https://github.com/)),想连那边的对话一起沉淀,切到 [`cc-connect` 分支](https://github.com/junyuan-fang/agentmemory-skills/tree/cc-connect)。

---

**Q:`ccskill` 这名字啥意思?**

A:就是个统一命令行入口(cc = Claude Code + skill),把底下 7 个脚本包成一个好记的命令。等于这套工具的「遥控器」。

---

## 命令速查

```
ccskill status                    自检:hook/定时任务/索引/画像注入 是否就位
ccskill index                     索引 / 增量更新(读 ~/.claude/projects)
ccskill recall <kw> [--summary]   搜历史对话(可选让 Claude 总结)
ccskill extract --date <d>        从对话提炼技能 SKILL.md
ccskill profile [--update]        查看 / 刷新用户画像
ccskill archive --date <d>        导出某天对话为 markdown
ccskill context --person <name>   注入某人在其他平台的近期上下文
ccskill list                      列出攒下的技能
ccskill show <slug>               查看某个技能
ccskill sync                      git pull + push
```

能力对 Hermes 的逐条实现见 [HERMES_PARITY.md](HERMES_PARITY.md);还没做 / 故意不做的见 [ROADMAP.md](ROADMAP.md)。

## License

[Apache License 2.0](LICENSE)
