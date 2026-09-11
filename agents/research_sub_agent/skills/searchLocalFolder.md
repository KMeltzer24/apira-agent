---
name: searchLocalFolder
description: Search on-disk stock research files by keyword.
---

# searchLocalFolder

Search the local stock-research corpus on disk (not vector search).
Implement the search in the code you generate — do **not** call Apira
Python modules, MCP tools, or other packaging modes.

## Contract

- **Args:** `query` (ticker or keyword; `*` / empty / `all` may mean match broadly).
- **Folder:** `${STOCK_RESEARCH_DIR}` (default `/data/stock-research`).
- Recursively find `.txt` / `.md` files under that folder (including `extracted/`).
- Skip `README.md` and AppleDouble `._*` files.
- Match when the query appears in the filename or file contents (case-insensitive).
- Cap large file bodies (e.g. ~32KB each) and stop after a reasonable total size.
- **Stdout:** print JSON with `query`, `folder`, `file_count`, and `files`
  (`filename`, `relative_path`, `content`).
- Cite only real files from your search; do not invent filenames.
