"""Tests for TOOL_MODE selection."""

from __future__ import annotations

import unittest

from agents.tool_mode import (
    TOOL_MODE_MCP,
    TOOL_MODE_PYTHON,
    TOOL_MODE_SKILLS_PROMPT,
    TOOL_MODE_SKILLS_SHELL,
    get_tool_mode,
)


class ToolModeTests(unittest.TestCase):
    def test_default_is_mcp(self) -> None:
        self.assertEqual(get_tool_mode(""), TOOL_MODE_MCP)

    def test_accepts_known_modes(self) -> None:
        for mode in (
            TOOL_MODE_MCP,
            TOOL_MODE_PYTHON,
            TOOL_MODE_SKILLS_PROMPT,
            TOOL_MODE_SKILLS_SHELL,
        ):
            self.assertEqual(get_tool_mode(mode), mode)
            self.assertEqual(get_tool_mode(mode.upper()), mode)

    def test_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            get_tool_mode("crewai")


if __name__ == "__main__":
    unittest.main()
