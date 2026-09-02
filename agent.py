"""Apira agent — LangGraph supervisor + specialists over MCP tools.

It connects to apira-mcp for backend tools and apira-rag for research tools,
then runs a user prompt through a supervisor graph (Gemini).

Run directly (`python agent.py`) for a one-shot demo with a hard-coded prompt,
or import `build_agent` / `run_agent` to serve it (see server.py).
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable

import httpx
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import (
    MCPToolCallRequest,
    MCPToolCallResult,
)

from graph import compile_supervisor_graph, reset_supervisor_hops
from logging_config import (
    REQUEST_ID_HEADER,
    configure_logging,
    get_request_id,
    log_event,
    normalize_user_id,
    set_user_id,
)

load_dotenv()
configure_logging()
logger = logging.getLogger(__name__)

# Always set via .env / docker-compose. This fallback matches the in-container
# EC2 deployment (the agent container reaches the MCP container's published port).
MCP_URL = os.environ.get("MCP_URL", "http://host.docker.internal:8000/mcp")
RAG_MCP_URL = os.environ.get(
    "RAG_MCP_URL", "http://host.docker.internal:8200/mcp"
)

# Gemini model that drives the agent (needs GOOGLE_API_KEY in the environment).
GEMINI_MODEL = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")

# Default prompt used by the one-shot CLI demo. The agent must work out that it
# needs to call `login` to get a user_id, then `get_portfolio`.
DEFAULT_PROMPT = (
    "Log in as user 'alice' with password 'password', then retrieve that "
    "user's portfolio and summarize the holdings."
)



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
    """Best-effort JSON object extraction from an MCP tool result."""
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
    """Extract correlatable business fields without secrets or full replies."""
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
        # get_portfolio args already have user_id; include it when present on payload.
        if payload.get("user_id") is not None:
            fields["user_id"] = payload["user_id"]
        return fields

    return {}


async def mcp_tool_logging_interceptor(
    request: MCPToolCallRequest,
    handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
) -> MCPToolCallResult:
    """Correlate and safely log one MCP tool invocation."""
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
        # Once login (or portfolio) reveals the user, stamp the rest of this request.
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


async def build_agent():
    """Load MCP tools and build a LangGraph agent backed by Gemini."""
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "agent.build.started",
        "Agent build started",
        model=GEMINI_MODEL,
    )
    try:
        client = MultiServerMCPClient(
            {
                "apira": {
                    "url": MCP_URL,
                    "transport": "streamable_http",
                    "httpx_client_factory": request_id_httpx_client_factory,
                },
                "research": {
                    "url": RAG_MCP_URL,
                    "transport": "streamable_http",
                    "httpx_client_factory": request_id_httpx_client_factory,
                },
            },
            tool_interceptors=[mcp_tool_logging_interceptor],
        )
        tools = await client.get_tools()
        # max_retries=0 so a 429 (quota) fails fast instead of honoring Gemini's
        # multi-second retry delay and hanging the request.
        model = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL, temperature=0, max_retries=0
        )
        agent = compile_supervisor_graph(model, tools)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "agent.build.failed",
            "Agent build failed",
            model=GEMINI_MODEL,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        raise

    log_event(
        logger,
        logging.INFO,
        "agent.build.completed",
        "Agent build completed",
        model=GEMINI_MODEL,
        tool_count=len(tools),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        agent_name="supervisor",
    )
    return agent


def _as_text(content) -> str:
    """Normalize a message's content to plain text.

    Gemini returns the final content as a list of blocks like
    [{"type": "text", "text": "..."}]; join the text parts into one string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


async def run_agent(agent, prompt: str) -> str:
    """Run one user prompt through the supervisor graph and return the final text."""
    reset_supervisor_hops()
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "agent.run.started",
        "Agent run started",
        prompt_length=len(prompt),
        model=GEMINI_MODEL,
        agent_name="supervisor",
    )
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"metadata": {"request_id": get_request_id()}},
        )
        reply = _as_text(result["messages"][-1].content)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "agent.run.failed",
            "Agent run failed",
            prompt_length=len(prompt),
            model=GEMINI_MODEL,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
            agent_name="supervisor",
        )
        raise

    log_event(
        logger,
        logging.INFO,
        "agent.run.completed",
        "Agent run completed",
        prompt_length=len(prompt),
        reply_length=len(reply),
        model=GEMINI_MODEL,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        agent_name="supervisor",
    )
    return reply


async def main() -> None:
    agent = await build_agent()
    print(f"User prompt: {DEFAULT_PROMPT}\n")
    print("Running agent...\n")
    answer = await run_agent(agent, DEFAULT_PROMPT)
    print("=== Agent answer ===")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
