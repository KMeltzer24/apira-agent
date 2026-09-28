"""Gemini model and MCP HTTP client shared by supervisor and specialists.

Each process passes only the MCP servers it is allowed to use so another
agent's tools are not even listed on the client.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Awaitable, Callable, Sequence

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import (
    MCPToolCallRequest,
    MCPToolCallResult,
)

from logging_config import (
    REQUEST_ID_HEADER,
    get_request_id,
    log_event,
    normalize_user_id,
    set_user_id,
)

logger = logging.getLogger(__name__)

MCP_URL = os.environ.get("MCP_URL", "http://host.docker.internal:8000/mcp")
RAG_MCP_URL = os.environ.get(
    "RAG_MCP_URL", "http://host.docker.internal:8200/mcp"
)
GEMINI_MODEL = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")

MCP_SERVER_SPECS = {
    "apira": {
        "url": MCP_URL,
        "transport": "streamable_http",
    },
    "research": {
        "url": RAG_MCP_URL,
        "transport": "streamable_http",
    },
}


def request_id_httpx_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Create an MCP HTTP client with the current request ID."""
    outbound_headers = dict(headers or {})
    request_id = get_request_id()
    if request_id:
        outbound_headers[REQUEST_ID_HEADER] = request_id
    return httpx.AsyncClient(headers=outbound_headers, timeout=timeout, auth=auth)


def _parse_tool_payload(result: MCPToolCallResult) -> dict | None:
    content = getattr(result, "content", None)
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                texts.append(block["text"])
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    texts.append(text)
    for text in texts:
        try:
            payload = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _safe_tool_result_fields(tool_name: str, result: MCPToolCallResult) -> dict:
    if getattr(result, "isError", False):
        return {}
    payload = _parse_tool_payload(result)
    if not payload:
        return {}

    if tool_name == "login":
        user_id = payload.get("user_id")
        return {"user_id": user_id} if user_id is not None else {}

    if tool_name == "get_portfolio":
        holdings = payload.get("holdings") or []
        if not isinstance(holdings, list):
            return {}
        tickers = [
            item.get("ticker")
            for item in holdings
            if isinstance(item, dict) and item.get("ticker")
        ]
        fields: dict = {
            "holdings_count": len(holdings),
            "tickers": tickers,
            "holdings_summary": [
                {"ticker": item.get("ticker"), "shares": item.get("shares")}
                for item in holdings
                if isinstance(item, dict)
            ],
        }
        if payload.get("user_id") is not None:
            fields["user_id"] = payload["user_id"]
        return fields

    return {}


async def mcp_tool_logging_interceptor(
    request: MCPToolCallRequest,
    handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
) -> MCPToolCallResult:
    request_id = get_request_id()
    if request_id:
        request = request.override(
            headers={**(request.headers or {}), REQUEST_ID_HEADER: request_id}
        )

    fields = {
        "tool_name": request.name,
        "upstream": request.server_name,
        "argument_keys": sorted(request.args),
    }
    if request.name == "get_portfolio" and "user_id" in request.args:
        fields["user_id"] = request.args["user_id"]

    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "mcp.tool.started",
        f"MCP tool {request.name} started",
        **fields,
    )
    try:
        result = await handler(request)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "mcp.tool.failed",
            f"MCP tool {request.name} failed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
            **fields,
        )
        raise

    event = "mcp.tool.failed" if getattr(result, "isError", False) else "mcp.tool.completed"
    level = logging.ERROR if event == "mcp.tool.failed" else logging.INFO
    result_fields = dict(fields)
    if event == "mcp.tool.failed":
        result_fields["error_type"] = "MCPToolError"
    else:
        result_fields.update(_safe_tool_result_fields(request.name, result))
        bound_user_id = normalize_user_id(result_fields.get("user_id"))
        if bound_user_id is not None:
            set_user_id(bound_user_id)
            if request.name == "get_portfolio" and "user_id" not in fields:
                fields["user_id"] = bound_user_id
    if event == "mcp.tool.failed":
        message = f"MCP tool {request.name} returned an error"
    else:
        message = f"MCP tool {request.name} completed via {request.server_name}"
    log_event(
        logger,
        level,
        event,
        message,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        **result_fields,
    )
    return result


def _mcp_connections(server_names: Sequence[str]) -> dict:
    missing = [name for name in server_names if name not in MCP_SERVER_SPECS]
    if missing:
        raise ValueError(f"Unknown MCP server names: {missing}")
    connections = {}
    for name in server_names:
        spec = dict(MCP_SERVER_SPECS[name])
        spec["httpx_client_factory"] = request_id_httpx_client_factory
        connections[name] = spec
    return connections


async def create_mcp_client_and_model(
    *,
    mcp_servers: Sequence[str],
):
    """Gemini plus an MCP client bound only to ``mcp_servers``."""
    client = MultiServerMCPClient(
        _mcp_connections(mcp_servers),
        tool_interceptors=[mcp_tool_logging_interceptor],
    )
    model = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL, temperature=0, max_retries=0
    )
    return model, client
