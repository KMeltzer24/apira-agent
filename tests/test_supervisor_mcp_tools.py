"""Tests for supervisor MCP allowlist (getPreviousRecommendation only)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents.supervisor.mcp_tools import TOOL_NAMES, select_tools


class SupervisorMcpToolsTests(unittest.TestCase):
    def test_selects_only_previous_recommendation_read(self) -> None:
        tools = [
            SimpleNamespace(name="login"),
            SimpleNamespace(name="getPreviousRecommendation"),
            SimpleNamespace(name="saveRecommendation"),
            SimpleNamespace(name="searchLocalFolder"),
        ]
        selected = select_tools(tools)
        self.assertEqual({t.name for t in selected}, TOOL_NAMES)
        self.assertNotIn("saveRecommendation", {t.name for t in selected})


if __name__ == "__main__":
    unittest.main()
