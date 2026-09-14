"""Tests for last-recommendation user_id extraction and the save hop."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.state import extract_user_id, last_ai_text
from agents.supervisor.save_recommendation import build_save_node


class ExtractUserIdTests(unittest.TestCase):
    def test_from_login_tool_message(self) -> None:
        messages = [
            ToolMessage(
                content=json.dumps({"user_id": 3}),
                name="login",
                tool_call_id="1",
            )
        ]
        self.assertEqual(extract_user_id(messages), 3)

    def test_fallback(self) -> None:
        self.assertEqual(extract_user_id([], fallback=9), 9)

    def test_last_ai_text(self) -> None:
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="Hold AAPL"),
        ]
        self.assertEqual(last_ai_text(messages), "Hold AAPL")


class SupervisorSaveTests(unittest.TestCase):
    def test_save_node_writes_when_user_id_and_body(self) -> None:
        node = build_save_node()
        with patch(
            "agents.supervisor.save_recommendation.save_recommendation",
            new=AsyncMock(),
        ) as save:
            asyncio.run(
                node(
                    {
                        "messages": [
                            HumanMessage(content="recommend"),
                            AIMessage(content="Trim TSLA Files: tsla-analysis.md"),
                        ],
                        "user_id": 2,
                    },
                    {},
                )
            )
        save.assert_awaited_once()
        self.assertEqual(save.await_args.args[0], 2)
        self.assertIn("Trim TSLA", save.await_args.args[1])

    def test_save_node_skips_without_user_id(self) -> None:
        node = build_save_node()
        with patch(
            "agents.supervisor.save_recommendation.save_recommendation",
            new=AsyncMock(),
        ) as save:
            asyncio.run(
                node(
                    {
                        "messages": [AIMessage(content="ok")],
                    },
                    {},
                )
            )
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
