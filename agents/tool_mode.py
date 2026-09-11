"""Select which tool packaging mode specialists use."""

from __future__ import annotations

import os

TOOL_MODE_MCP = "mcp"
TOOL_MODE_PYTHON = "python"
TOOL_MODE_SKILLS_PROMPT = "skills_prompt"
TOOL_MODE_SKILLS_SHELL = "skills_shell"

TOOL_MODES = frozenset(
    {
        TOOL_MODE_MCP,
        TOOL_MODE_PYTHON,
        TOOL_MODE_SKILLS_PROMPT,
        TOOL_MODE_SKILLS_SHELL,
    }
)

DEFAULT_TOOL_MODE = TOOL_MODE_MCP


def get_tool_mode(raw: str | None = None) -> str:
    """Return a validated TOOL_MODE (default: mcp)."""
    value = (raw if raw is not None else os.environ.get("TOOL_MODE", DEFAULT_TOOL_MODE))
    mode = (value or DEFAULT_TOOL_MODE).strip().lower()
    if mode not in TOOL_MODES:
        raise ValueError(
            f"Invalid TOOL_MODE={value!r}; expected one of {sorted(TOOL_MODES)}"
        )
    return mode
