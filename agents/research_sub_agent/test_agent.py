"""Run the research specialist without compiling the supervisor graph.

    python -m unittest agents.research_sub_agent.test_agent
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from agents.research_sub_agent.agent import build_agent
from agents.research_sub_agent.mcp_tools import TOOL_NAMES
from agents.tool_mode import (
    TOOL_MODE_MCP,
    TOOL_MODE_PYTHON,
    TOOL_MODE_SKILLS_PROMPT,
    TOOL_MODE_SKILLS_SHELL,
)


class _BindableFake(FakeListChatModel):
    """FakeListChatModel does not implement bind_tools; create_agent requires it."""

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self

_RESEARCH_REPLY = "AAPL Hold Files: aapl-outlook.md. MSFT Add Files: msft-analysis.md."


class _FakeMcpClient:
    def __init__(self, tools: list) -> None:
        self._tools = tools
        self.get_tools_calls = 0

    async def get_tools(self) -> list:
        self.get_tools_calls += 1
        return list(self._tools)


def _mcp_catalog() -> list:
    @tool
    def login(username: str, password: str) -> str:
        """Log in (should be ignored by this specialist)."""
        return '{"user_id": 1}'

    @tool
    def searchLocalFolder(query: str) -> str:
        """Search files."""
        return "[]"

    @tool
    def searchVectorDB(query: str) -> str:
        """Search vectors."""
        return "[]"

    return [login, searchLocalFolder, searchVectorDB]


def _invoke(node, prompt: str) -> dict:
    return asyncio.run(
        node(
            {"messages": [HumanMessage(content=prompt)]},
            {},
        )
    )


class ResearchSubAgentTests(unittest.TestCase):
    def test_python_mode_runs_without_supervisor(self) -> None:
        model = _BindableFake(responses=[_RESEARCH_REPLY])
        with patch.dict(os.environ, {"TOOL_MODE": TOOL_MODE_PYTHON}):
            node = asyncio.run(build_agent(model, client=None))
        result = _invoke(
            node,
            "Holdings: AAPL 150, MSFT 80. Use searchLocalFolder only.",
        )
        texts = [getattr(m, "content", "") for m in result["messages"]]
        self.assertTrue(any(_RESEARCH_REPLY in str(text) for text in texts))

    def test_mcp_uses_passed_tools_and_skips_client(self) -> None:
        model = _BindableFake(responses=[_RESEARCH_REPLY])
        client = _FakeMcpClient(_mcp_catalog())
        with patch.dict(os.environ, {"TOOL_MODE": TOOL_MODE_MCP}):
            node = asyncio.run(
                build_agent(model, client, tools=_mcp_catalog())
            )
        self.assertEqual(client.get_tools_calls, 0)
        result = _invoke(node, "Research AAPL with searchLocalFolder.")
        self.assertTrue(result["messages"])

    def test_mcp_loads_allowlist_from_client(self) -> None:
        model = _BindableFake(responses=[_RESEARCH_REPLY])
        catalog = _mcp_catalog()
        client = _FakeMcpClient(catalog)
        with patch.dict(os.environ, {"TOOL_MODE": TOOL_MODE_MCP}):
            asyncio.run(build_agent(model, client))
        self.assertEqual(client.get_tools_calls, 1)
        selected = {t.name for t in catalog if t.name in TOOL_NAMES}
        self.assertEqual(selected, set(TOOL_NAMES))

    def test_skills_modes_build(self) -> None:
        for mode in (TOOL_MODE_SKILLS_PROMPT, TOOL_MODE_SKILLS_SHELL):
            model = _BindableFake(responses=[_RESEARCH_REPLY])
            with patch.dict(os.environ, {"TOOL_MODE": mode, "SKILLS_MCP": "false"}):
                node = asyncio.run(build_agent(model, client=None))
            result = _invoke(node, "Research AAPL with searchLocalFolder.")
            self.assertTrue(result["messages"], msg=mode)

    def test_skills_mcp_mode_builds_with_both_search_tools(self) -> None:
        for mode in (TOOL_MODE_SKILLS_PROMPT, TOOL_MODE_SKILLS_SHELL):
            model = _BindableFake(responses=[_RESEARCH_REPLY])
            with patch.dict(os.environ, {"TOOL_MODE": mode, "SKILLS_MCP": "true"}):
                node = asyncio.run(build_agent(model, client=None))
            result = _invoke(node, "Research AAPL with searchVectorDB.")
            self.assertTrue(result["messages"], msg=mode)

    def test_unsupported_mode_raises(self) -> None:
        model = _BindableFake(responses=["ok"])
        with patch.dict(os.environ, {"TOOL_MODE": "crewai"}):
            with self.assertRaises(ValueError):
                asyncio.run(build_agent(model, client=None))


if __name__ == "__main__":
    unittest.main()
