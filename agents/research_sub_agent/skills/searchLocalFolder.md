---
name: searchLocalFolder
description: Search on-disk stock research files by keyword.
---

# searchLocalFolder

Use when the user asks for local-folder / file-based research (not vector search).

Rules:
- Prefer the tickers already present in the conversation (from portfolio holdings).
- Search per ticker unless the user asks for a single combined query.
- Cite filenames from results; do not invent research files.
- Format each holding as Hold/Add/Trim with short reasoning and cited files.
