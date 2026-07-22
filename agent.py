"""Apira agent — a LangGraph agent that uses Apira's MCP tools.

It connects to apira-mcp for backend tools and apira-rag for research tools,
then runs a user prompt through the Gemini API.

Run directly (`python agent.py`) for a one-shot demo with a hard-coded prompt,
or import `build_agent` / `run_agent` to serve it (see server.py).
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import (
    MCPToolCallRequest,
    MCPToolCallResult,
)

from logging_config import (
    REQUEST_ID_HEADER,
    configure_logging,
    get_request_id,
    log_event,
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

SYSTEM_PROMPT = (
    "You are a portfolio assistant for the Apira system. "
    "You have tools to log in a user, fetch a portfolio, search stock research "
    "files on disk via searchLocalFolder, and semantic search via searchVectorDB (pgvector). "
    "To get a portfolio you first need the user_id returned by the login tool. "
    "Always log in first, then call get_portfolio with that user_id. "
    "Report the holdings clearly to the user. "
    "For stock recommendations: follow the user's instruction about which research tool to use — "
    "searchLocalFolder OR searchVectorDB, never both unless explicitly asked. "
    "After fetching the portfolio, search per ticker with the chosen tool. "
    "Format each holding as: ticker and action (Hold/Add/Trim), then cited filenames, "
    "then one or two short sentences of reasoning. "
    "Be concise — no sector overview, no holdings summary list."
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
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "mcp.tool.started",
        "MCP tool call started",
        **fields,
    )
    try:
        result = await handler(request)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "mcp.tool.failed",
            "MCP tool call failed",
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
    log_event(
        logger,
        level,
        event,
        "MCP tool call failed" if event == "mcp.tool.failed" else "MCP tool call completed",
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
        agent = create_agent(model, tools, system_prompt=SYSTEM_PROMPT)
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
    """Run one user prompt through the agent and return the final text answer."""
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "agent.run.started",
        "Agent run started",
        prompt_length=len(prompt),
        model=GEMINI_MODEL,
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
