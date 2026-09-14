"""MCP tools owned by the supervisor (logged-in read of last recommendation)."""

from __future__ import annotations

from typing import Any, Sequence

TOOL_NAMES = frozenset({"getPreviousRecommendation"})


def select_tools(tools: Sequence[Any]) -> list[Any]:
    """Keep only supervisor MCP tools from a shared client tool list."""
    return [t for t in tools if getattr(t, "name", None) in TOOL_NAMES]


async def load_tools(client: Any) -> list[Any]:
    """Load MCP tools from the shared client and keep this agent's allowlist."""
    return select_tools(await client.get_tools())
