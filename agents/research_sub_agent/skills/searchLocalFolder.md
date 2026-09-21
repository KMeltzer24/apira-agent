# searchLocalFolder

Search the local stock-research corpus on disk (not vector search, not MCP).
Do **not** import Apira `python_tools`, `mcp_tools`, or other skill files.
Do **not** call RAG MCP.

## Contract

- **Args:** `query` (ticker or keyword). Empty / `*` / `all` means match broadly.
- **Folder:** `${STOCK_RESEARCH_DIR}` (default `/data/stock-research`).
- Recursively find `.txt` / `.md` files (including `extracted/`).
- Skip `README.md` and AppleDouble `._*` files.
- Match when the query appears in the filename or file contents (case-insensitive).
- Cap large file bodies (~32KB each) and stop after a reasonable total size (~96KB).
- **Stdout:** print JSON with `query`, `folder`, `file_count`, and `files`
  (`filename`, `relative_path`, `content`).
- Cite only real files from this search. Do not invent filenames or file text.
