---
name: searchLocalFolder
description: Search on-disk stock-research files; sample bash is a hint.
---

# searchLocalFolder

Search the local stock-research corpus on disk (not vector search).
Implement the search in the code you generate — do **not** call Apira
Python modules, MCP tools, or other packaging modes. Sample bash below is only a hint.

## Contract

- **Args:** `query`.
- **Folder:** `${STOCK_RESEARCH_DIR}`.
- Recursively search `.txt` / `.md` (including `extracted/`); case-insensitive match on name or contents.
- **Stdout:** JSON with `query`, `folder`, `file_count`, and `files`
  (`filename`, `relative_path`, `content`).
- Do not invent filenames.

## Sample bash (hint — adapt or rewrite in your generated fence)

```bash
set -euo pipefail
ROOT="${STOCK_RESEARCH_DIR:-/data/stock-research}"
Q="${query:-}"
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

Note: the sample uses a one-shot `python3` heredoc for JSON convenience. That is
**inline generated-style code**, not `agents.research_sub_agent` or `python_tools`.
