"""MCP client is bound only to the servers a process is allowed to use."""

from __future__ import annotations

import unittest

from agents.llm_mcp import _mcp_connections


class McpServerIsolationTests(unittest.TestCase):
    def test_portfolio_does_not_list_research_server(self) -> None:
        connections = _mcp_connections(["apira"])
        self.assertEqual(set(connections), {"apira"})

    def test_research_does_not_list_apira_server(self) -> None:
        connections = _mcp_connections(["research"])
        self.assertEqual(set(connections), {"research"})

    def test_unknown_server_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _mcp_connections(["other-agent"])


if __name__ == "__main__":
    unittest.main()
