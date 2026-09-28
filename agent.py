"""Apira agent — LangGraph supervisor over A2A specialists.

The supervisor process connects only to apira-mcp (last-rec tools). Portfolio
and research are other containers; this process does not load their MCP servers.

Run directly (`python agent.py`) for a one-shot demo with a hard-coded prompt,
or import `build_agent` / `run_agent` to serve it (see server.py).
"""

import asyncio
import logging
import time

from dotenv import load_dotenv

from agents.graph import compile_supervisor_graph, reset_supervisor_hops
from agents.llm_mcp import (
    GEMINI_MODEL,
    create_mcp_client_and_model,
    mcp_tool_logging_interceptor,
    request_id_httpx_client_factory,
)
from logging_config import (
    configure_logging,
    get_request_id,
    log_event,
)

load_dotenv()
configure_logging()
logger = logging.getLogger(__name__)

# CLI demo: login then holdings, without naming tools in the prompt.
DEFAULT_PROMPT = (
    "Log in as user 'alice' with password 'password', then retrieve that "
    "user's portfolio and summarize the holdings."
)

__all__ = [
    "GEMINI_MODEL",
    "build_agent",
    "create_mcp_client_and_model",
    "mcp_tool_logging_interceptor",
    "request_id_httpx_client_factory",
    "run_agent",
]


async def build_agent():
    """Load supervisor MCP tools and build a LangGraph agent backed by Gemini."""
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "agent.build.started",
        "Agent build started",
        model=GEMINI_MODEL,
    )
    try:
        model, client = await create_mcp_client_and_model(mcp_servers=["apira"])
        agent = await compile_supervisor_graph(model, client)
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
