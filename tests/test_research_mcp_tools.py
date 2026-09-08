"""Tests for research MCP tool selection."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents.research_sub_agent.mcp_tools import TOOL_NAMES, select_tools


class ResearchMcpToolsTests(unittest.TestCase):
    def test_selects_only_research_tools(self) -> None:
        tools = [
            SimpleNamespace(name="login"),
            SimpleNamespace(name="searchLocalFolder"),
            SimpleNamespace(name="searchVectorDB"),
            SimpleNamespace(name="unrelated"),
        ]
        selected = select_tools(tools)
        self.assertEqual({t.name for t in selected}, TOOL_NAMES)

    def test_empty_stays_empty(self) -> None:
        self.assertEqual(select_tools([]), [])


if __name__ == "__main__":
    unittest.main()
