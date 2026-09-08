"""Build the research specialist node (create_agent + logging wrap)."""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig

from agents.research_sub_agent.mcp_tools import load_tools, select_tools
from agents.research_sub_agent.prompt import RESEARCH_PROMPT
from agents.state import GraphState
from logging_config import log_event

logger = logging.getLogger(__name__)

AGENT_NAME = "research"


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
        return {"messages": result["messages"]}

    return _node


async def build_agent(
    model: Any,
    client: Any,
    *,
    tools: Sequence[Any] | None = None,
):
    """Build a graph node for the research specialist using this agent's MCP tools.

    Pass ``tools`` when the shared client was already fetched once by the graph.
    """
    selected = select_tools(tools) if tools is not None else await load_tools(client)
    subgraph = create_agent(
        model,
        selected,
        system_prompt=RESEARCH_PROMPT,
        name=AGENT_NAME,
    )
    return _wrap_specialist(subgraph)
