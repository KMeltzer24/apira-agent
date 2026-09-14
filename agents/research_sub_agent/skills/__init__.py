"""Skills for the research sub-agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pydantic import Field

from agents.skills_runtime import make_codegen_skill_tool
from agents.tool_mode import skills_mcp_enabled

SKILLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _local_search_env() -> dict[str, str]:
    return {
        "STOCK_RESEARCH_DIR": os.environ.get(
            "STOCK_RESEARCH_DIR", "/data/stock-research"
        ),
        "PYTHONPATH": os.environ.get("PYTHONPATH", str(_REPO_ROOT)),
        "PYTHON_BIN": sys.executable,
    }


def _rag_mcp_env() -> dict[str, str]:
    return {
        "RAG_MCP_URL": os.environ.get(
            "RAG_MCP_URL", "http://host.docker.internal:8200/mcp"
        ),
        "PYTHON_BIN": sys.executable,
    }


def _folder_tool(model: Any, *, kind: str, mcp: bool) -> Any:
    return make_codegen_skill_tool(
        model=model,
        tool_name="searchLocalFolder",
        skills_dir=SKILLS_DIR,
        description=(
            "Search text and Markdown stock research via RAG MCP."
            if mcp
            else "Search text and Markdown stock research in the stock-research folder."
        ),
        arg_fields={
            "query": (str, Field("", description="Search query")),
        },
        kind=kind,  # type: ignore[arg-type]
        extra_env=_rag_mcp_env if mcp else _local_search_env,
        mcp=mcp,
        timeout_sec=90.0 if mcp else 60.0,
    )


def _vector_tool(model: Any, *, kind: str) -> Any:
    return make_codegen_skill_tool(
        model=model,
        tool_name="searchVectorDB",
        skills_dir=SKILLS_DIR,
        description="Search stock research in pgvector via RAG MCP.",
        arg_fields={
            "query": (str, Field("", description="Search query")),
        },
        kind=kind,  # type: ignore[arg-type]
        extra_env=_rag_mcp_env,
        mcp=True,
        timeout_sec=90.0,
    )


def _build_tools(model: Any, *, kind: str) -> list[Any]:
    mcp = skills_mcp_enabled()
    tools = [_folder_tool(model, kind=kind, mcp=mcp)]
    if mcp:
        tools.append(_vector_tool(model, kind=kind))
    return tools


def load_prompt_tools(model: Any) -> list[Any]:
    """Codegen tools driven by NL ``searchLocalFolder.md`` (or ``*_MCP.md``)."""
    return _build_tools(model, kind="prompt")


def load_shell_tools(model: Any) -> list[Any]:
    """Codegen tools driven by ``*_shell.md`` (or ``*_shell_MCP.md``)."""
    return _build_tools(model, kind="shell")
