"""Supervisor save hop after research (GET is a logged-in supervisor tool)."""

from __future__ import annotations

import logging
import time

from langchain_core.runnables import RunnableConfig

from agents.state import GraphState, last_ai_text
from agents.supervisor.python_tools import save_recommendation
from logging_config import log_event

logger = logging.getLogger(__name__)

SAVE_AGENT_NAME = "save_recommendation"


def build_save_node():
    """Persist the last research reply. Research never writes the table."""

    async def save_recommendation_node(
        state: GraphState, config: RunnableConfig
    ) -> dict:
        del config
        started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "agent.run.started",
            "save_recommendation started",
            agent_name=SAVE_AGENT_NAME,
        )
        user_id = state.get("user_id")
        body = last_ai_text(state.get("messages"))
        try:
            if user_id is not None and body:
                await save_recommendation(int(user_id), body)
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "agent.run.failed",
                "save_recommendation failed",
                agent_name=SAVE_AGENT_NAME,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )
            raise
        log_event(
            logger,
            logging.INFO,
            "agent.run.completed",
            "save_recommendation completed",
            agent_name=SAVE_AGENT_NAME,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {}

    return save_recommendation_node
