"""A2A payload and remote specialist node tests (Nacos/A2A mocked)."""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from agents.a2a.discover import discover_agent_card
from agents.a2a.nodes import build_remote_specialist_node
from agents.a2a.payload import decode_state, encode_state
from agents.graph import compile_supervisor_graph
from agents.tool_mode import TOOL_MODE_MCP


class _BindableFake(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self


class _FakeMcpClient:
    def __init__(self, tools: list) -> None:
        self._tools = tools
        self.get_tools_calls = 0

    async def get_tools(self) -> list:
        self.get_tools_calls += 1
        return list(self._tools)


def _demo_tools() -> list:
    @tool
    def getPreviousRecommendation(user_id: int) -> str:
        """Last rec."""
        return "none"

    return [getPreviousRecommendation]


class PayloadTests(unittest.TestCase):
    def test_roundtrip_messages_and_user_id(self) -> None:
        state = {
            "messages": [HumanMessage(content="hello")],
            "logged_in": True,
            "user_id": 1,
        }
        decoded = decode_state(encode_state(state))
        self.assertTrue(decoded["logged_in"])
        self.assertEqual(decoded["user_id"], 1)
        self.assertEqual(decoded["messages"][0].content, "hello")

    def test_plain_text_fallback(self) -> None:
        decoded = decode_state("just a user prompt")
        self.assertEqual(decoded["messages"][0].content, "just a user prompt")


class RemoteNodeTests(unittest.TestCase):
    def test_portfolio_node_uses_a2a_caller(self) -> None:
        node = build_remote_specialist_node("portfolio")
        remote_state = {
            "messages": [AIMessage(content="holdings listed")],
            "logged_in": True,
            "user_id": 7,
        }
        with patch(
            "agents.a2a.nodes.call_specialist",
            new=AsyncMock(return_value=remote_state),
        ) as mocked:
            result = asyncio.run(
                node(
                    {"messages": [HumanMessage(content="login")]},
                    {},
                )
            )
        mocked.assert_awaited_once()
        self.assertEqual(result["user_id"], 7)
        self.assertTrue(result["logged_in"])
        self.assertEqual(result["messages"][0].content, "holdings listed")


class GraphCompileStillSequentialTests(unittest.TestCase):
    def test_graph_does_not_import_in_process_specialists(self) -> None:
        model = _BindableFake(responses=["ok"])
        client = _FakeMcpClient(_demo_tools())
        with patch.dict(os.environ, {"TOOL_MODE": TOOL_MODE_MCP}):
            graph = asyncio.run(compile_supervisor_graph(model, client))
        self.assertIn("portfolio", graph.nodes)
        self.assertIn("research", graph.nodes)
        self.assertEqual(client.get_tools_calls, 1)


class DiscoverTests(unittest.TestCase):
    def test_discover_uses_nacos_only(self) -> None:
        card = object()
        with patch(
            "agents.a2a.discover.NacosAgentCardResolver.get_agent_card",
            new=AsyncMock(return_value=card),
        ) as mocked:
            result = asyncio.run(
                discover_agent_card("portfolio", attempts=1, delay_seconds=0)
            )
        self.assertIs(result, card)
        mocked.assert_awaited_once()

    def test_discover_does_not_fall_back_to_http(self) -> None:
        with patch(
            "agents.a2a.discover.NacosAgentCardResolver.get_agent_card",
            new=AsyncMock(side_effect=RuntimeError("not registered")),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(
                    discover_agent_card("research", attempts=1, delay_seconds=0)
                )
        self.assertIn("Could not discover A2A agent 'research'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
