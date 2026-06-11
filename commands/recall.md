---
description: Search past conversation history via FTS5 index. Optionally summarize.
---

Search the SQLite FTS5 index of past conversations.

```bash
ccskill recall "$ARGUMENTS"
```

If the user asked for a summary ("总结" / "summary" / "summarize"), append `--summary`:

```bash
ccskill recall "$ARGUMENTS" --summary
```

Show the output. Briefly comment on cross-match patterns if relevant.
