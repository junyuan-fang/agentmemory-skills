---
description: View or refresh the user profile (Honcho-lite).
---

If `$ARGUMENTS` contains `update` / `refresh`, refresh first then show; else just show:

```bash
ccskill profile --update   # when updating
ccskill profile            # view only
```

Use the underlying script's `--reset` flag if asked to rebuild from scratch.
