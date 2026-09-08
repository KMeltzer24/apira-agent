"""Supervisor node: structured routing, hop limit, no tools."""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from agents.state import GraphState
from agents.supervisor.prompt import SUPERVISOR_PROMPT
from logging_config import log_event

logger = logging.getLogger(__name__)

MAX_SUPERVISOR_HOPS = 6

_supervisor_hops: ContextVar[int] = ContextVar("supervisor_hops", default=0)


class SupervisorDecision(BaseModel):
    next: Literal["portfolio", "research", "finish"] = Field(
        description="Who should run next, or finish the turn."
    )
    reply: str = Field(
        default="",
        description="User-facing text when next is finish and specialists have not answered.",
    )


def reset_supervisor_hops() -> None:
    """Reset the per-request hop counter (call at the start of each run)."""
    _supervisor_hops.set(0)


def parse_supervisor_decision(raw: Any) -> SupervisorDecision:
    """Normalize structured or loosely parsed supervisor output."""
    if isinstance(raw, SupervisorDecision):
        return raw
    if isinstance(raw, dict):
        nxt = str(raw.get("next", "finish")).strip().lower()
        if nxt not in {"portfolio", "research", "finish"}:
            nxt = "finish"
        return SupervisorDecision(next=nxt, reply=str(raw.get("reply") or ""))
    text = getattr(raw, "content", raw)
    if not isinstance(text, str):
        text = str(text)
    lowered = text.lower()
    nxt: Literal["portfolio", "research", "finish"] = "finish"
    if "research" in lowered:
        nxt = "research"
    elif "portfolio" in lowered or "login" in lowered:
        nxt = "portfolio"
    return SupervisorDecision(next=nxt, reply="")


def build_node(model: Any):
    """Return the async supervisor graph node (routing only)."""
    try:
        structured = model.with_structured_output(SupervisorDecision)
    except NotImplementedError:
        structured = None

    async def supervisor_node(state: GraphState) -> Command:
        hops = _supervisor_hops.get() + 1
        _supervisor_hops.set(hops)
        started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "agent.run.started",
            "supervisor hop started",
            agent_name="supervisor",
        )
        forced_finish = hops > MAX_SUPERVISOR_HOPS
        try:
            if forced_finish:
                decision = SupervisorDecision(next="finish", reply="")
            else:
                route_messages = [
                    {"role": "system", "content": SUPERVISOR_PROMPT},
                    *state["messages"],
                ]
                if structured is not None:
                    raw = await structured.ainvoke(route_messages)
                else:
                    raw = await model.ainvoke(route_messages)
                decision = parse_supervisor_decision(raw)
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "agent.run.failed",
                "supervisor hop failed",
                agent_name="supervisor",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )
            raise

        next_node = "finish" if forced_finish else decision.next
        log_event(
            logger,
            logging.INFO,
            "agent.run.completed",
            f"supervisor routed to {next_node}",
            agent_name="supervisor",
            next_node=next_node,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        if next_node == "finish":
            if decision.reply.strip():
                return Command(
                    update={"messages": [AIMessage(content=decision.reply)]},
                    goto=END,
                )
            return Command(goto=END)
        return Command(goto=next_node)

    return supervisor_node
