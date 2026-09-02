"""Tests for MCP tool partition and the supervisor StateGraph."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.tools import tool

from graph import (
    PORTFOLIO_TOOL_NAMES,
    RESEARCH_TOOL_NAMES,
    compile_supervisor_graph,
    parse_supervisor_decision,
    partition_mcp_tools,
)


class PartitionTests(unittest.TestCase):
    def test_splits_known_tools_and_reports_others(self) -> None:
        tools = [
            SimpleNamespace(name="login"),
            SimpleNamespace(name="get_portfolio"),
            SimpleNamespace(name="searchLocalFolder"),
            SimpleNamespace(name="searchVectorDB"),
            SimpleNamespace(name="unrelated"),
        ]
        portfolio, research, other = partition_mcp_tools(tools)
        self.assertEqual({t.name for t in portfolio}, PORTFOLIO_TOOL_NAMES)
        self.assertEqual({t.name for t in research}, RESEARCH_TOOL_NAMES)
        self.assertEqual(other, ["unrelated"])

    def test_empty_tools_stay_empty(self) -> None:
        portfolio, research, other = partition_mcp_tools([])
        self.assertEqual(portfolio, [])
        self.assertEqual(research, [])
        self.assertEqual(other, [])


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
        graph = compile_supervisor_graph(
            model, [login, get_portfolio, searchLocalFolder, searchVectorDB]
        )
        self.assertIn("supervisor", graph.nodes)
        self.assertIn("portfolio", graph.nodes)
        self.assertIn("research", graph.nodes)

        portfolio, research, other = partition_mcp_tools(
            [login, get_portfolio, searchLocalFolder, searchVectorDB]
        )
        self.assertEqual(len(portfolio), 2)
        self.assertEqual(len(research), 2)
        self.assertEqual(other, [])
        self.assertNotIn("login", {t.name for t in research})
        self.assertNotIn("searchVectorDB", {t.name for t in portfolio})


if __name__ == "__main__":
    unittest.main()
