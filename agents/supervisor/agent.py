"""Supervisor nodes: guest then logged-in routing, hop limit, no tools."""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any, Literal, Sequence

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from agents.state import GraphState
from agents.supervisor.prompt import LOGGED_IN_SUPERVISOR_PROMPT, SUPERVISOR_PROMPT
from logging_config import log_event

logger = logging.getLogger(__name__)

MAX_SUPERVISOR_HOPS = 6
_RESEARCH_REQUEST_MARKERS = (
    "searchlocalfolder",
    "searchvectordb",
    "recommend",
    "hold / add / trim",
    "hold/add/trim",
    "hold, add, or trim",
)
_RESEARCH_TOOL_NAMES = frozenset({"searchLocalFolder", "searchVectorDB"})

_supervisor_hops: ContextVar[int] = ContextVar("supervisor_hops", default=0)

GuestNext = Literal["portfolio", "finish"]
LoggedInNext = Literal["research", "finish"]
SupervisorNext = Literal["portfolio", "research", "finish"]


class SupervisorDecision(BaseModel):
    next: SupervisorNext = Field(
        description="Who should run next, or finish the turn."
    )
    reply: str = Field(
        default="",
        description="User-facing text when next is finish and specialists have not answered.",
    )


class GuestDecision(BaseModel):
    next: GuestNext = Field(
        description="Portfolio specialist, or finish. Research is not allowed until logged in."
    )
    reply: str = Field(
        default="",
        description="User-facing text when next is finish and specialists have not answered.",
    )


class LoggedInDecision(BaseModel):
    next: LoggedInNext = Field(
        description="Research specialist, or finish. Portfolio already ran."
    )
    reply: str = Field(
        default="",
        description="User-facing text when next is finish and specialists have not answered.",
    )


def reset_supervisor_hops() -> None:
    """Reset the per-request hop counter (call at the start of each run)."""
    _supervisor_hops.set(0)


def parse_supervisor_decision(
    raw: Any,
    *,
    allowed: frozenset[str] | None = None,
) -> SupervisorDecision:
    """Normalize structured or loosely parsed supervisor output."""
    allowed_next = allowed or frozenset({"portfolio", "research", "finish"})
    if isinstance(raw, (SupervisorDecision, GuestDecision, LoggedInDecision)):
        nxt = raw.next
        reply = raw.reply
    elif isinstance(raw, dict):
        nxt = str(raw.get("next", "finish")).strip().lower()
        reply = str(raw.get("reply") or "")
    else:
        text = getattr(raw, "content", raw)
        if not isinstance(text, str):
            text = str(text)
        lowered = text.lower()
        nxt = "finish"
        if "research" in lowered:
            nxt = "research"
        elif "portfolio" in lowered or "login" in lowered:
            nxt = "portfolio"
        reply = ""
    if nxt not in allowed_next:
        if nxt == "research" and "portfolio" in allowed_next:
            nxt = "portfolio"
        else:
            nxt = "finish"
    return SupervisorDecision(next=nxt, reply=reply)


def _is_human_message(message: Any) -> bool:
    if isinstance(message, HumanMessage) or getattr(message, "type", None) == "human":
        return True
    if isinstance(message, dict) and str(message.get("role", "")).lower() in {
        "user",
        "human",
    }:
        return True
    return False


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content or "")


def user_requested_research(messages: Sequence[Any]) -> bool:
    """True when the original user ask needs research / recommendations."""
    for message in messages:
        if not _is_human_message(message):
            continue
        text = _message_text(message).casefold()
        if any(marker in text for marker in _RESEARCH_REQUEST_MARKERS):
            return True
    return False


def research_tools_already_used(messages: Sequence[Any]) -> bool:
    """True when searchLocalFolder / searchVectorDB already appear in the thread."""
    for message in messages:
        name = getattr(message, "name", None)
        if name in _RESEARCH_TOOL_NAMES:
            return True
        for tool_call in getattr(message, "tool_calls", None) or []:
            tool_name = (
                tool_call.get("name")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "name", None)
            )
            if tool_name in _RESEARCH_TOOL_NAMES:
                return True
    return False


def enforce_guest_routing(
    decision: SupervisorDecision,
    messages: Sequence[Any],
    *,
    forced_finish: bool = False,
) -> SupervisorDecision:
    """Guest supervisor: research is closed; research asks go to portfolio first."""
    if forced_finish:
        return SupervisorDecision(next="finish", reply=decision.reply)
    if decision.next == "research":
        return SupervisorDecision(next="portfolio", reply="")
    if decision.next == "finish" and user_requested_research(messages):
        return SupervisorDecision(next="portfolio", reply="")
    return decision


def enforce_research_routing(
    decision: SupervisorDecision,
    messages: Sequence[Any],
    *,
    forced_finish: bool = False,
) -> SupervisorDecision:
    """Logged-in supervisor: if the user asked for research and it has not run, do not finish."""
    if forced_finish or decision.next != "finish":
        return decision
    if user_requested_research(messages) and not research_tools_already_used(messages):
        return SupervisorDecision(next="research", reply="")
    return decision


def build_node(model: Any, *, logged_in: bool = False):
    """Return a supervisor graph node.

    ``logged_in=False`` is the guest hop (portfolio or finish only).
    ``logged_in=True`` is the post-portfolio hop (research or finish only).
    """
    schema = LoggedInDecision if logged_in else GuestDecision
    prompt = LOGGED_IN_SUPERVISOR_PROMPT if logged_in else SUPERVISOR_PROMPT
    allowed = (
        frozenset({"research", "finish"})
        if logged_in
        else frozenset({"portfolio", "finish"})
    )
    agent_name = "logged_in" if logged_in else "supervisor"
    try:
        structured = model.with_structured_output(schema)
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
            agent_name=agent_name,
        )
        forced_finish = hops > MAX_SUPERVISOR_HOPS
        try:
            if forced_finish:
                decision = SupervisorDecision(next="finish", reply="")
            else:
                route_messages = [
                    {"role": "system", "content": prompt},
                    *state["messages"],
                ]
                if structured is not None:
                    raw = await structured.ainvoke(route_messages)
                else:
                    raw = await model.ainvoke(route_messages)
                decision = parse_supervisor_decision(raw, allowed=allowed)
                if logged_in:
                    decision = enforce_research_routing(
                        decision,
                        state["messages"],
                        forced_finish=forced_finish,
                    )
                else:
                    decision = enforce_guest_routing(
                        decision,
                        state["messages"],
                        forced_finish=forced_finish,
                    )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "agent.run.failed",
                "supervisor hop failed",
                agent_name=agent_name,
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
            agent_name=agent_name,
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
