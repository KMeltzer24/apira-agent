"""Tests for in-process python tool packaging."""

from __future__ import annotations

import unittest

from agents.portfolio_sub_agent.mcp_tools import TOOL_NAMES as PORTFOLIO_NAMES
from agents.portfolio_sub_agent.python_tools import load_tools as load_portfolio
from agents.research_sub_agent.mcp_tools import TOOL_NAMES as RESEARCH_NAMES
from agents.research_sub_agent.python_tools import load_tools as load_research


class PythonToolsTests(unittest.TestCase):
    def test_portfolio_names_match_mcp(self) -> None:
        tools = load_portfolio()
        self.assertEqual([t.name for t in tools], ["login", "get_portfolio"])
        self.assertEqual({t.name for t in tools}, set(PORTFOLIO_NAMES))

    def test_research_python_is_local_folder_only(self) -> None:
        tools = load_research()
        self.assertEqual([t.name for t in tools], ["searchLocalFolder"])
        self.assertTrue(set(t.name for t in tools).issubset(set(RESEARCH_NAMES)))


if __name__ == "__main__":
    unittest.main()
