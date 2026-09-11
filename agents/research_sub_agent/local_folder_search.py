"""Local stock-research folder search (non-MCP path for searchLocalFolder)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ALLOWED_EXTENSIONS = {".txt", ".md"}
MAX_FILE_BYTES = 32_000
MAX_TOTAL_BYTES = 96_000


def _resolve_research_dir(root: str | Path | None = None) -> Path:
    path = Path(
        root
        if root is not None
        else os.environ.get("STOCK_RESEARCH_DIR", "/data/stock-research")
    ).resolve()
    if not path.is_dir():
        raise FileNotFoundError(
            f"Stock research folder not found: {path}. "
            "Mount stock-research/ or set STOCK_RESEARCH_DIR."
        )
    return path


def _read_text_file(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="replace")
    content = content.replace("\x00", "")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        content = content[:MAX_FILE_BYTES] + "\n\n[truncated]"
    return content


def _file_matches_query(path: Path, content: str, query: str) -> bool:
    if not query or query.strip() in {"*", "all"}:
        return True
    needle = query.casefold()
    return needle in path.name.casefold() or needle in content.casefold()


def search_local_folder(query: str = "", *, root: str | Path | None = None) -> dict[str, Any]:
    """Search ``.txt`` / ``.md`` files under the stock-research folder."""
    research_root = _resolve_research_dir(root)
    matches: list[dict[str, str]] = []
    total_bytes = 0

    for path in sorted(research_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        if path.name.startswith("._") or path.name.lower() == "readme.md":
            continue
        if not path.resolve().is_relative_to(research_root):
            continue

        content = _read_text_file(path)
        if not _file_matches_query(path, content, query):
            continue

        size = len(content.encode("utf-8"))
        if total_bytes + size > MAX_TOTAL_BYTES:
            break
        matches.append(
            {
                "filename": path.name,
                "relative_path": str(path.relative_to(research_root)),
                "content": content,
            }
        )
        total_bytes += size

    return {
        "query": query or "all",
        "folder": str(research_root),
        "file_count": len(matches),
        "files": matches,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m agents.research_sub_agent.local_folder_search [query]``."""
    args = list(sys.argv[1:] if argv is None else argv)
    query = args[0] if args else ""
    try:
        result = search_local_folder(query)
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
