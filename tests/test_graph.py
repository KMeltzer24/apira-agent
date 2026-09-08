"""Tests for supervisor StateGraph wiring and decision parsing."""

from __future__ import annotations

import asyncio
import unittest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import tool

from agents.graph import compile_supervisor_graph
from agents.supervisor.agent import parse_supervisor_decision


class _FakeMcpClient:
    def __init__(self, tools: list) -> None:
        self._tools = tools

    async def get_tools(self) -> list:
        return list(self._tools)


class SupervisorDecisionTests(unittest.TestCase):
    def test_parse_dict_and_invalid_next(self) -> None:
        parsed = parse_supervisor_decision({"next": "PORTFOLIO", "reply": "hi"})
        self.assertEqual(parsed.next, "portfolio")
        self.assertEqual(parsed.reply, "hi")
        fallback = parse_supervisor_decision({"next": "tools"})
        self.assertEqual(fallback.next, "finish")


class GraphCompileTests(unittest.TestCase):
    def test_compiled_graph_has_supervisor_and_specialists(self) -> None:
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

        model = FakeListChatModel(responses=["ok"])
        client = _FakeMcpClient(
            [login, get_portfolio, searchLocalFolder, searchVectorDB]
        )
        graph = asyncio.run(compile_supervisor_graph(model, client))
        self.assertIn("supervisor", graph.nodes)
        self.assertIn("portfolio", graph.nodes)
        self.assertIn("research", graph.nodes)


if __name__ == "__main__":
    unittest.main()
