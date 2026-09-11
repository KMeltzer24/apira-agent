"""Skills for the research sub-agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pydantic import Field

from agents.skills_runtime import make_codegen_skill_tool

SKILLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[3]

# searchVectorDB stays MCP-only; skills cover local folder search.


def _local_search_env() -> dict[str, str]:
    return {
        "STOCK_RESEARCH_DIR": os.environ.get(
            "STOCK_RESEARCH_DIR", "/data/stock-research"
        ),
        "PYTHONPATH": os.environ.get("PYTHONPATH", str(_REPO_ROOT)),
        "PYTHON_BIN": sys.executable,
    }


def _build_tools(model: Any, *, kind: str) -> list[Any]:
    return [
        make_codegen_skill_tool(
            model=model,
            tool_name="searchLocalFolder",
            skills_dir=SKILLS_DIR,
            description=(
                "Search text and Markdown stock research in the stock-research folder."
            ),
            arg_fields={
                "query": (str, Field("", description="Search query")),
            },
            kind=kind,  # type: ignore[arg-type]
            extra_env=_local_search_env,
        )
    ]


def load_prompt_tools(model: Any) -> list[Any]:
    """Codegen tools driven by NL ``searchLocalFolder.md``."""
    return _build_tools(model, kind="prompt")


def load_shell_tools(model: Any) -> list[Any]:
    """Codegen tools driven by ``searchLocalFolder_shell.md`` (sample as hint)."""
    return _build_tools(model, kind="shell")
