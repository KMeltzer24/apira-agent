"""Tests for supervisor StateGraph wiring and decision parsing."""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import tool

from agents.graph import compile_supervisor_graph
from agents.supervisor.agent import parse_supervisor_decision
from agents.tool_mode import (
    TOOL_MODE_MCP,
    TOOL_MODE_PYTHON,
    TOOL_MODE_SKILLS_PROMPT,
    TOOL_MODE_SKILLS_SHELL,
)


class _FakeMcpClient:
    def __init__(self, tools: list) -> None:
        self._tools = tools
        self.get_tools_calls = 0

    async def get_tools(self) -> list:
        self.get_tools_calls += 1
        return list(self._tools)


def _demo_tools() -> list:
    @tool
    def login(username: str, password: str) -> str:
        """Log in."""
        return "1"

    @tool
    def get_portfolio(user_id: int) -> str:
        """Fetch holdings."""
        return "[]"

    @tool
    def searchLocalFolder(query: str) -> str:
        """Search files."""
        return ""

    @tool
    def searchVectorDB(query: str) -> str:
        """Search vectors."""
        return ""

    return [login, get_portfolio, searchLocalFolder, searchVectorDB]


class SupervisorDecisionTests(unittest.TestCase):
    def test_parse_dict_and_invalid_next(self) -> None:
        parsed = parse_supervisor_decision({"next": "PORTFOLIO", "reply": "hi"})
        self.assertEqual(parsed.next, "portfolio")
        self.assertEqual(parsed.reply, "hi")
        fallback = parse_supervisor_decision({"next": "tools"})
        self.assertEqual(fallback.next, "finish")


class GraphCompileTests(unittest.TestCase):
    def test_compiled_graph_has_supervisor_and_specialists(self) -> None:
        model = FakeListChatModel(responses=["ok"])
        client = _FakeMcpClient(_demo_tools())
        with patch.dict(os.environ, {"TOOL_MODE": TOOL_MODE_MCP}):
            graph = asyncio.run(compile_supervisor_graph(model, client))
        self.assertIn("supervisor", graph.nodes)
        self.assertIn("portfolio", graph.nodes)
        self.assertIn("research", graph.nodes)
        self.assertEqual(client.get_tools_calls, 1)

    def test_non_mcp_modes_skip_client_get_tools(self) -> None:
        model = FakeListChatModel(responses=["ok"])
        for mode in (
            TOOL_MODE_PYTHON,
            TOOL_MODE_SKILLS_PROMPT,
            TOOL_MODE_SKILLS_SHELL,
        ):
            client = _FakeMcpClient(_demo_tools())
            with patch.dict(os.environ, {"TOOL_MODE": mode}):
                graph = asyncio.run(compile_supervisor_graph(model, client))
            self.assertIn("portfolio", graph.nodes)
            self.assertEqual(client.get_tools_calls, 0, msg=mode)


if __name__ == "__main__":
    unittest.main()
