"""LangGraph nodes that invoke remote A2A specialists."""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.a2a.client import call_specialist
from agents.state import GraphState
from logging_config import log_event

logger = logging.getLogger(__name__)


def build_remote_specialist_node(agent_name: str):
    """Return a graph node that discovers and calls ``agent_name`` over A2A."""

    async def _node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
        started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "agent.run.started",
            f"{agent_name} specialist started",
            agent_name=agent_name,
        )
        try:
            result = await call_specialist(agent_name, dict(state))
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "agent.run.failed",
                f"{agent_name} specialist failed",
                agent_name=agent_name,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )
            raise
        log_event(
            logger,
            logging.INFO,
            "agent.run.completed",
            f"{agent_name} specialist completed",
            agent_name=agent_name,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        update: dict[str, Any] = {"messages": result["messages"]}
        if "logged_in" in result:
            update["logged_in"] = result["logged_in"]
        if "user_id" in result:
            update["user_id"] = result["user_id"]
        elif agent_name == "portfolio":
            update["logged_in"] = True
        return update

    return _node
