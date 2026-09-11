"""In-process LangChain @tool implementations for the research specialist."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from agents.research_sub_agent.local_folder_search import search_local_folder


@tool
async def searchLocalFolder(query: str = "") -> str:
    """Search text and Markdown stock research in the stock-research folder."""
    return json.dumps(search_local_folder(query))


def load_tools() -> list[Any]:
    """Return research python tools (local folder search only)."""
    return [searchLocalFolder]
