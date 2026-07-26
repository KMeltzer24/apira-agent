"""Focused tests for structured logging and request correlation."""

from __future__ import annotations

import io
import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

import server
from agent import (
    mcp_tool_logging_interceptor,
    request_id_httpx_client_factory,
    run_agent,
)
from logging_config import (
    JsonFormatter,
    REQUEST_ID_HEADER,
    log_event,
    reset_request_id,
    set_request_id,
    set_user_id,
    reset_user_id,
)


class LogCapture:
    def __init__(self, name: str) -> None:
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(JsonFormatter())
        self.logger = logging.getLogger(name)
        self.logger.handlers = [self.handler]
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)

    def records(self) -> list[dict]:
        return [
            json.loads(line)
            for line in self.stream.getvalue().splitlines()
            if line.strip()
        ]


class JsonLoggingTests(unittest.TestCase):
    def test_json_output_has_required_fields_and_redacts_sensitive_values(self) -> None:
        capture = LogCapture("test.json")
        token = set_request_id("4b45ab5f-b1f5-45cd-9248-f7ad7d20caaa")
        try:
            log_event(
                capture.logger,
                logging.INFO,
                "test.completed",
                "Safe test event",
                status_code=200,
                password="do-not-log",
            )
        finally:
            reset_request_id(token)

        record = capture.records()[0]
        self.assertEqual(record["event"], "test.completed")
        self.assertEqual(record["request_id"], "4b45ab5f-b1f5-45cd-9248-f7ad7d20caaa")
        self.assertEqual(record["password"], "[REDACTED]")
        self.assertEqual(record["status_code"], 200)
        self.assertTrue(
            {
                "timestamp",
                "level",
                "service",
                "environment",
                "event",
                "message",
                "request_id",
            }.issubset(record)
        )

    def test_json_output_includes_user_id_context(self) -> None:
        capture = LogCapture("test.user")
        request_token = set_request_id("4b45ab5f-b1f5-45cd-9248-f7ad7d20caaa")
        user_token = set_user_id(1)
        try:
            log_event(
                capture.logger,
                logging.INFO,
                "test.with_user",
                "Event with user context",
            )
        finally:
            reset_user_id(user_token)
            reset_request_id(request_token)

        record = capture.records()[0]
        self.assertEqual(record["user_id"], 1)
        self.assertEqual(record["event"], "test.with_user")


class CorrelationTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_id_is_in_langgraph_metadata(self) -> None:
        request_id = "64058ca9-b303-4f61-b34b-8f22992c9965"
        message = SimpleNamespace(content="reply")
        fake_agent = SimpleNamespace(
            ainvoke=AsyncMock(return_value={"messages": [message]})
        )
        token = set_request_id(request_id)
        try:
            self.assertEqual(await run_agent(fake_agent, "private prompt"), "reply")
        finally:
            reset_request_id(token)

        config = fake_agent.ainvoke.await_args.kwargs["config"]
        self.assertEqual(config["metadata"]["request_id"], request_id)

    async def test_dynamic_mcp_headers_and_logs_never_include_argument_values(self) -> None:
        capture = LogCapture("agent")
        request_id = "64eef762-0888-44b3-a427-19fa08b548ee"
        request = MCPToolCallRequest(
            name="login",
            args={"username": "alice", "password": "very-secret"},
            server_name="apira",
        )
        seen_request = None

        async def handler(outbound_request):
            nonlocal seen_request
            seen_request = outbound_request
            return SimpleNamespace(
                isError=False,
                content=[{"type": "text", "text": '{"user_id": 1, "success": true}'}],
            )

        token = set_request_id(request_id)
        try:
            with patch("agent.logger", capture.logger):
                await mcp_tool_logging_interceptor(request, handler)
        finally:
            reset_request_id(token)

        self.assertEqual(seen_request.headers[REQUEST_ID_HEADER], request_id)
        output = capture.stream.getvalue()
        self.assertIn('"argument_keys":["password","username"]', output)
        self.assertIn('"user_id":1', output)
        self.assertNotIn("alice", output)
        self.assertNotIn("very-secret", output)

    async def test_portfolio_tool_logs_tickers_without_prompt_text(self) -> None:
        capture = LogCapture("agent")
        request = MCPToolCallRequest(
            name="get_portfolio",
            args={"user_id": 1},
            server_name="apira",
        )

        async def handler(_outbound_request):
            return SimpleNamespace(
                isError=False,
                content=[
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "holdings": [
                                    {"ticker": "AAPL", "shares": 150},
                                    {"ticker": "TSLA", "shares": 60},
                                ]
                            }
                        ),
                    }
                ],
            )

        with patch("agent.logger", capture.logger):
            await mcp_tool_logging_interceptor(request, handler)

        output = capture.stream.getvalue()
        self.assertIn('"tickers":["AAPL","TSLA"]', output)
        self.assertIn('"user_id":1', output)
        self.assertNotIn("password", output)

    async def test_http_client_factory_reads_current_request_id_each_time(self) -> None:
        first = "c4af7aa7-bdd9-4b2e-9343-30b0a18da3e2"
        second = "d947e7bc-d5c6-4031-bd50-9426913a5d57"
        clients = []
        for request_id in (first, second):
            token = set_request_id(request_id)
            try:
                client = request_id_httpx_client_factory(
                    headers={"X-Static": "present"},
                    timeout=httpx.Timeout(1),
                )
                clients.append(client)
                self.assertEqual(client.headers[REQUEST_ID_HEADER], request_id)
                self.assertEqual(client.headers["X-Static"], "present")
            finally:
                reset_request_id(token)
        for client in clients:
            await client.aclose()


class RequestMiddlewareTests(unittest.TestCase):
    def test_valid_request_id_is_echoed_on_chat_response(self) -> None:
        request_id = "305ca8cf-7148-483b-b8a6-c071808aaefd"
        with (
            patch("server.get_agent", new=AsyncMock(return_value=object())),
            patch("server.run_agent", new=AsyncMock(return_value="safe reply")),
            TestClient(server.app) as client,
        ):
            response = client.post(
                "/chat",
                headers={REQUEST_ID_HEADER: request_id},
                json={"message": "sensitive prompt"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers[REQUEST_ID_HEADER], request_id)
        self.assertEqual(response.json(), {"reply": "safe reply"})

    def test_invalid_request_id_is_replaced(self) -> None:
        with TestClient(server.app) as client:
            response = client.get(
                "/health", headers={REQUEST_ID_HEADER: "not-a-valid-uuid"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers[REQUEST_ID_HEADER], "not-a-valid-uuid")
        self.assertEqual(len(response.headers[REQUEST_ID_HEADER]), 36)


if __name__ == "__main__":
    unittest.main()
