# searchLocalFolder

Search the local stock-research corpus on disk (not vector search, not MCP).
Do **not** import Apira `python_tools`, `mcp_tools`, or other skill files.

## Contract

- **Args:** `query`. Empty / `*` / `all` means match broadly.
- **Folder:** `${STOCK_RESEARCH_DIR}` (default `/data/stock-research`).
- Recursively search `.txt` / `.md` (including `extracted/`).
- Skip `README.md` and AppleDouble `._*` files.
- Case-insensitive match on filename or contents.
- Cap large file bodies (~32KB each) and stop after a reasonable total size (~96KB).
- **Stdout:** JSON with `query`, `folder`, `file_count`, and `files`
  (`filename`, `relative_path`, `content`).
- Cite only real files from this search. Do not invent filenames or file text.

## Sample bash

```bash
set -euo pipefail
export STOCK_RESEARCH_DIR="${STOCK_RESEARCH_DIR:-/data/stock-research}"
export query="${query:-}"
python3 - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["STOCK_RESEARCH_DIR"]).resolve()
q = (os.environ.get("query") or "").casefold()
match_all = q in {"", "*", "all"}
files = []
total = 0
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.suffix.lower() not in {".txt", ".md"}:
        continue
    if path.name.startswith("._") or path.name.lower() == "readme.md":
        continue
    text = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    if len(text.encode()) > 32000:
        text = text[:32000] + "\n\n[truncated]"
    if not match_all and q not in path.name.casefold() and q not in text.casefold():
        continue
    size = len(text.encode())
    if total + size > 96000:
        break
    files.append({
        "filename": path.name,
        "relative_path": str(path.relative_to(root)),
        "content": text,
    })
    total += size
print(json.dumps({
    "query": os.environ.get("query") or "all",
    "folder": str(root),
    "file_count": len(files),
    "files": files,
}))
PY
```
