---
name: searchLocalFolder
description: Search on-disk stock-research files locally (no MCP).
---

# searchLocalFolder

Call this skill with `query`. It searches the local stock-research folder and prints JSON matches.

```bash
"${PYTHON_BIN:-python}" -m agents.research_sub_agent.local_folder_search \
  "${query}"
```
