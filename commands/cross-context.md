---
description: Pull this user's recent activity from OTHER platforms (cross-platform memory).
---

When the user references another platform ("继续昨天那个项目" / "上次我在 Telegram 说过…"),
inject context from their other-platform user_keys.

Read the session's user_key from your agent / IM bridge's session data, then:

```bash
ccskill context $ARGUMENTS
```

Typical args:
- `--user-key <their key>`   (this person's stable id on the current platform)
- `--person <name>`          (if mapped in data/identities.json)
- `--days 30`                (longer lookback)
- `--raw`                    (skip LLM summary)

No mapping → prints nothing (expected). To map a person on a second platform,
edit `data/identities.json` (see data/identities.example.json).
