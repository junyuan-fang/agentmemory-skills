**English** | [简体中文](README.md)

# agentmemory-skills

**Give Claude Code long-term memory and self-improvement — without spending a single extra cent on API calls.**

Claude Code is powerful, but it has one flaw: **every new session starts with amnesia**. How you fixed that bug last week, the naming convention you settled on last month, the preferences you've explained a hundred times — all gone the moment you close the window. You end up re-explaining everything, again and again.

`agentmemory-skills` fixes that. It quietly reads the chat transcripts Claude Code already stores on your machine, and:

- 🔍 **Remembers every conversation** — search any of it back with one command ("how did we write that deploy script?")
- 🧠 **Distills recurring operations into reusable "skills"** that get sharper with use
- 👤 **Gradually learns your preferences and work style**, and applies them proactively
- 🔁 **Remembers you across devices/platforms** (with an IM bridge)

The key: all the "thinking" runs through your **existing Claude Code subscription** (via the `claude -p` command). **No metered API calls. No extra cost.**

> Inspired by [Hermes from Nous Research](https://github.com/nousresearch/hermes-agent) — but Hermes bills per token through the Claude API, while this project reuses your subscription. $0 extra.

---

## One example to get it instantly

**Without it**:
```
You (new session): How did we solve that SQLite lock issue last time?
Claude:            I don't have memory of previous conversations. Could you describe it?
You:               (sigh, starts re-explaining…)
```

**With it**:
```
$ ccskill recall "SQLite lock"
[05-28 14:02] user   | getting "database is locked" on concurrent writes
[05-28 14:03] assist | switch to WAL mode: PRAGMA journal_mode=WAL, set busy_timeout…

$ ccskill recall "SQLite lock" --summary
--- Summary ---
Last conclusion: for concurrent SQLite writes use WAL + busy_timeout=5000;
fine for single-writer-multi-reader; move to Postgres for real concurrency.
```

One command brings back a conclusion from three weeks ago — no scrolling through history, no re-asking Claude.

---

## What you can do with it

After installing you get one command, `ccskill` (plus a few optional `/slash-commands`):

| You want to | Command | What it does |
|---|---|---|
| Search past conversations | `ccskill recall "keyword"` | Full-text search across all Claude Code sessions, in milliseconds |
| Search + summarize | `ccskill recall "keyword" --summary` | Pipes the matches to Claude for a distilled summary |
| Turn conversations into skills | `ccskill extract --date yesterday` | Claude reads your chats and writes reusable `SKILL.md` files |
| View/refresh your profile | `ccskill profile --update` | Summarizes your preferences, stack, and habits into markdown |
| List accumulated skills | `ccskill list` | See the workflows distilled so far |
| Export a day's backup | `ccskill archive --date 2026-06-01` | Human-readable markdown archive |

---

## Install: one command, fully automatic afterwards

**Prerequisites**: you already use the [Claude Code](https://claude.com/claude-code) CLI (`claude` runs in your terminal) + Python 3. That's all.

### Linux / macOS / WSL / Git Bash

```bash
git clone https://github.com/junyuan-fang/agentmemory-skills.git
cd agentmemory-skills
./install.sh
```

### Windows (native PowerShell)

```powershell
git clone https://github.com/junyuan-fang/agentmemory-skills.git
cd agentmemory-skills
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

**That's it — no further configuration.** `install` automatically:

- ✅ Puts the `ccskill` command on PATH (usable from any directory)
- ✅ Indexes all your existing Claude Code sessions
- ✅ Installs the **distill-on-session-end** hook (written into `~/.claude/settings.json`; backed up, idempotent)
- ✅ Installs the **daily scheduled distillation** (cron on Linux/mac, Task Scheduler on Windows)
- ✅ Copies `/recall`, `/skill-extract`, `/profile` etc. into `~/.claude/commands/`
- ✅ Skills land in `~/.claude/skills/`, profile gets imported into `~/.claude/CLAUDE.md` — **picked up automatically by every new Claude session**

Then just use Claude Code as usual; memory and skills accumulate in the background. **Open a new terminal** and verify:

```bash
ccskill status                      # self-check: hook / scheduler / index / profile import all in place?
ccskill recall "something you discussed recently"
```

> ⚠️ Cloning the repo and running a few scripts ≠ installed. The automation (hook + scheduled
> tasks) must be registered via `install`. In doubt, run `ccskill status` — any ✗ means run install again.

> Re-running `install` is safe (idempotent). To remove everything: `./install.sh --uninstall` (Windows: `install.ps1 -Uninstall`).
> Per-session distillation too heavy? See [`hooks/README.md`](hooks/README.md) to switch to index-only.

---

## Three distillation triggers, active right after install

"Distillation" = turning conversations into memory and skills. `install` sets up all three triggers — nothing for you to do:

| Trigger | When | Installed by |
|---|---|---|
| **① Distill on close** | Every time you exit a Claude session → index + extract that session | SessionEnd hook |
| **② Scheduled** | Hourly indexing; daily 03:30 skill extraction, 04:00 profile refresh | cron / Task Scheduler |
| **③ On demand** | Send `/skill-extract` inside a conversation | slash command |

All three write the same database without conflicts. Logs go to `data/cron.log`; `tail -f data/cron.log` to watch it run.

<details>
<summary>Don't want the install script? Manual setup / customization (expand)</summary>

- **Command only**: `ln -s "$PWD/scripts/ccskill" ~/.local/bin/ccskill` (Windows: add `scripts` to PATH, use `ccskill.cmd`), then `ccskill index`.
- **① Distill-on-close hook**: put the absolute path of [`hooks/distill-on-end.sh`](hooks/distill-on-end.sh) (Windows: `.ps1`) into `hooks.SessionEnd` of `~/.claude/settings.json`. Details in [`hooks/README.md`](hooks/README.md).
- **② Scheduled distillation**: Linux/mac — adapt [`cron/crontab.example`](cron/crontab.example) and `crontab -e`; Windows — register with `schtasks` (ready-made commands inside install.ps1).
- **③ Slash commands**: copy the `.md` files under [`commands/`](commands/) into `~/.claude/commands/`.
- Per-session extraction too heavy: comment out the `extract-skill` call in `hooks/distill-on-end.*`, keep indexing only, and let the daily job handle extraction.

</details>

## Why it costs nothing extra

Most similar tools (Hermes included) call the Claude **API** for memory/summarization — billed **per token**, separately from your Claude subscription. You'd be paying twice for the same model.

In this project, everything that needs "AI thinking" (summaries, skill extraction, profile updates) goes through the `claude -p` command — **reusing the Claude Code you're already logged into**. Roughly 4–10 calls a day, all within your subscription quota. **API bill: $0.**

| | API-based tools | This project |
|---|---|---|
| Each AI call | Billed per token, extra cost | Reuses Claude subscription, $0 extra |
| Where data lives | Usually the cloud | All local (SQLite + markdown) |
| Dependencies | Cloud service / API key | One machine + Claude Code. Done. |

---

## agentmemory-skills vs Hermes: who has what

| Capability | Hermes | This project |
|---|:---:|:---:|
| Long-term memory + full-text search (FTS5) | ✅ | ✅ |
| Self-evolving skills (chat → skill, sharper with use) | ✅ | ✅ |
| Automatic distillation (no manual trigger) | ✅ | ✅ hook + cron |
| Cross-platform conversation continuity | ✅ | ✅ needs identity mapping |
| User modeling / profile | ✅ Honcho dialectic | ⚠️ single-pass LLM summary |
| Isolated parallel sub-agents | ✅ | ❌ deliberately not |
| Hibernate / wake-on-demand cost saving | ✅ | ❌ not planned |
| 200+ model routing (OpenRouter) | ✅ | ❌ would break the zero-cost positioning |
| RL trajectory / Atropos | ✅ | ❌ |
| **Cost per AI call** | 💸 API, per token | ✅ **reuses Claude subscription, $0 extra** |
| **Data / deployment** | ☁️ mostly cloud | ✅ **all local, one machine** |

In one sentence: **core memory capabilities are on par; we win on cost and locality; the heavy distributed features (sub-agents / hibernation / model routing) are Hermes' strengths we deliberately skip.**

> Per-capability implementation details in [HERMES_PARITY.md](HERMES_PARITY.md); trade-offs and plans for the ⚠️/❌ items in [ROADMAP.md](ROADMAP.md).

---

## How it works

```
You chat with Claude Code as usual
        │
        ▼   Claude Code writes a transcript for every session
   ~/.claude/projects/**/*.jsonl        ← the project's only data source (read-only)
        │
        ▼   "sediment" distillation (hook / cron / manual)
   ┌──────────────┬────────────────┬─────────────────┐
   index into SQLite   distill SKILL.md    update user profile    archive to markdown
   (instant search)    (sharper with use)  (auto-injected)        (human-readable backup)
        │
        ▼
   you pull any of it back via ccskill / slash commands
```

Design principles: **never touch Claude Code itself** (read its records only), **pure filesystem** (SQLite + markdown — easy to back up and grep), **cron/hook driven** (no resident process).

---

## FAQ

**Q: Does it read conversations from all my Claude Code projects?**

A: Yes, it indexes everything under `~/.claude/projects/` by default. The database `data/sessions.db` stays on your machine and is never uploaded anywhere.

---

**Q: Will my conversations leak to GitHub?**

A: No. All personal data (database, archives, profiles, logs) is excluded by `.gitignore`; this repository **contains code only**.

---

**Q: What exactly is "skill extraction"?**

A: Claude reads your conversations, spots "you've done this more than once / will do it again", and writes a `SKILL.md` (with steps and commands). When the same topic comes up again it **merges and upgrades** the old and new versions (v2, v3, …), getting better over time.

Skills land directly in **`~/.claude/skills/<slug>/`** — Claude Code's global skills directory, **auto-discovered and invoked by every new session**, zero extra configuration. To change the location (e.g. keep skills version-controlled inside this repo) set `AGENTMEMORY_SKILLS_DIR`. Same for the profile: install adds one `@import` line to `~/.claude/CLAUDE.md`, so every new session carries your profile.

---

**Q: Do I need an IM (WeChat / Feishu / Telegram)?**

A: No. The `master` branch reads Claude Code CLI records directly. If you use Claude **through an IM bridge** (e.g. cc-connect) and want those conversations distilled too, switch to the [`cc-connect` branch](https://github.com/junyuan-fang/agentmemory-skills/tree/cc-connect).

---

**Q: What does the name `ccskill` mean?**

A: It's the unified CLI entry point (cc = Claude Code + skill) wrapping the 7 underlying scripts into one memorable command. The "remote control" of this toolkit.

---

## Command cheatsheet

```
ccskill status                    self-check: hook / scheduler / index / profile import
ccskill index                     index / incremental update (reads ~/.claude/projects)
ccskill recall <kw> [--summary]   search history (optionally summarized by Claude)
ccskill extract --date <d>        distill skills from conversations into SKILL.md
ccskill profile [--update]        view / refresh the user profile
ccskill archive --date <d>        export a day's conversations to markdown
ccskill context --person <name>   inject someone's recent cross-platform context
ccskill list                      list accumulated skills
ccskill show <slug>               view one skill
ccskill sync                      git pull + push
```

Per-capability comparison with Hermes in [HERMES_PARITY.md](HERMES_PARITY.md); not-yet / deliberately-skipped items in [ROADMAP.md](ROADMAP.md).

## License

[Apache License 2.0](LICENSE)
