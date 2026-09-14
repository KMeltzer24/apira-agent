"""Build the portfolio specialist node (create_agent + logging wrap)."""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig

from agents.portfolio_sub_agent.mcp_tools import load_tools as load_mcp_tools
from agents.portfolio_sub_agent.mcp_tools import select_tools
from agents.portfolio_sub_agent.prompt import PORTFOLIO_PROMPT
from agents.portfolio_sub_agent.python_tools import load_tools as load_python_tools
from agents.portfolio_sub_agent.skills import (
    load_prompt_tools,
    load_shell_tools,
)
from agents.state import GraphState, extract_user_id
from agents.tool_mode import (
    TOOL_MODE_MCP,
    TOOL_MODE_PYTHON,
    TOOL_MODE_SKILLS_PROMPT,
    TOOL_MODE_SKILLS_SHELL,
    get_tool_mode,
)
from logging_config import log_event

logger = logging.getLogger(__name__)

AGENT_NAME = "portfolio"


def _wrap_specialist(subgraph: Any):
    """Run the specialist subgraph and log without leaking prompts."""

    async def _node(state: GraphState, config: RunnableConfig) -> dict:
        started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "agent.run.started",
            f"{AGENT_NAME} specialist started",
            agent_name=AGENT_NAME,
        )
        try:
            result = await subgraph.ainvoke({"messages": state["messages"]}, config)
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "agent.run.failed",
                f"{AGENT_NAME} specialist failed",
                agent_name=AGENT_NAME,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )
            raise
        log_event(
            logger,
            logging.INFO,
            "agent.run.completed",
            f"{AGENT_NAME} specialist completed",
            agent_name=AGENT_NAME,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {
            "messages": result["messages"],
            "logged_in": True,
            "user_id": extract_user_id(result["messages"], state.get("user_id")),
        }

    return _node


async def build_agent(
    model: Any,
    client: Any,
    *,
    tools: Sequence[Any] | None = None,
):
    """Build a graph node for the portfolio specialist.

    Pass ``tools`` when the shared MCP client was already fetched once by the graph
    (used when ``TOOL_MODE=mcp``).
    """
    mode = get_tool_mode()
    if mode == TOOL_MODE_MCP:
        selected_tools = (
            select_tools(tools) if tools is not None else await load_mcp_tools(client)
        )
        prompt = PORTFOLIO_PROMPT
    elif mode == TOOL_MODE_PYTHON:
        selected_tools = load_python_tools()
        prompt = PORTFOLIO_PROMPT
    elif mode == TOOL_MODE_SKILLS_PROMPT:
        selected_tools = load_prompt_tools(model)
        prompt = PORTFOLIO_PROMPT
    elif mode == TOOL_MODE_SKILLS_SHELL:
        selected_tools = load_shell_tools(model)
        prompt = PORTFOLIO_PROMPT
    else:
        raise ValueError(f"Unsupported TOOL_MODE for portfolio: {mode}")

    subgraph = create_agent(
        model,
        selected_tools,
        system_prompt=prompt,
        name=AGENT_NAME,
    )
    return _wrap_specialist(subgraph)
