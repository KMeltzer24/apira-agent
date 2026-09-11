"""Skills for the research sub-agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pydantic import Field

from agents.skills_runtime import load_prompt_skills, make_shell_skill_tool

SKILLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[3]

# searchVectorDB stays MCP-only; skills cover local folder search.
_TOOL_ORDER = ("searchLocalFolder",)


def load_prompt_skill_text() -> str:
    """NL-only skills for system-prompt injection."""
    return load_prompt_skills(SKILLS_DIR, _TOOL_ORDER)


def _local_search_env() -> dict[str, str]:
    return {
        "STOCK_RESEARCH_DIR": os.environ.get(
            "STOCK_RESEARCH_DIR", "/data/stock-research"
        ),
        "PYTHONPATH": os.environ.get("PYTHONPATH", str(_REPO_ROOT)),
        "PYTHON_BIN": sys.executable,
    }


def load_shell_tools() -> list[Any]:
    """Tools that execute embedded bash from ``*_shell.md``."""
    return [
        make_shell_skill_tool(
            tool_name="searchLocalFolder",
            skills_dir=SKILLS_DIR,
            description="Search text and Markdown stock research in the stock-research folder.",
            arg_fields={
                "query": (str, Field("", description="Search query")),
            },
            extra_env=_local_search_env,
        )
    ]
