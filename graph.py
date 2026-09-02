"""LangGraph supervisor + specialist subgraphs.

The parent graph is explicit: START → supervisor → portfolio | research → supervisor → END.
Specialists are create_agent subgraphs with partitioned MCP tools. The supervisor
is the conversational agent: it answers directly or routes; there is no third chat node.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Annotated, Any, Literal, Sequence

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from logging_config import log_event

logger = logging.getLogger(__name__)

PORTFOLIO_TOOL_NAMES = frozenset({"login", "get_portfolio"})
RESEARCH_TOOL_NAMES = frozenset({"searchLocalFolder", "searchVectorDB"})
MAX_SUPERVISOR_HOPS = 6

_supervisor_hops: ContextVar[int] = ContextVar("supervisor_hops", default=0)

PORTFOLIO_PROMPT = (
    "You are the Apira portfolio specialist. "
    "You have tools to log in a user and fetch a portfolio. "
    "To get a portfolio you first need the user_id returned by the login tool. "
    "Always log in first, then call get_portfolio with that user_id. "
    "Report the holdings clearly. Do not search research files or recommend trades."
)

RESEARCH_PROMPT = (
    "You are the Apira research specialist. "
    "You have searchLocalFolder (files on disk) and searchVectorDB (pgvector). "
    "Follow the user's instruction about which research tool to use — "
    "searchLocalFolder OR searchVectorDB, never both unless explicitly asked. "
    "Use holdings and tickers already in the conversation; do not invent holdings. "
    "Search per ticker with the chosen tool. "
    "Format each holding as: ticker and action (Hold/Add/Trim), then cited filenames, "
    "then one or two short sentences of reasoning. "
    "Be concise — no sector overview, no holdings summary list."
)

SUPERVISOR_PROMPT = (
    "You are the Apira supervisor (the chat agent). You do not call MCP tools. "
    "You route work to specialists or finish with a user-facing answer.\n"
    "Choose next:\n"
    "- portfolio: login, holdings, or any request that needs user_id / get_portfolio.\n"
    "- research: stock research, recommendations, Hold/Add/Trim, searchLocalFolder, "
    "or searchVectorDB. If the conversation does not yet contain holdings, choose "
    "portfolio first; you will be called again after that specialist returns.\n"
    "- finish: greetings, how Apira works, or the specialists have already produced "
    "the final answer.\n"
    "Do not send a specialist that already completed that job in this turn. "
    "For recommendations: portfolio, then research, then finish. "
    "When finishing after a specialist, leave reply empty so their last message is shown. "
    "When finishing without a specialist, put the user-facing answer in reply."
)


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


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


def partition_mcp_tools(tools: Sequence[Any]) -> tuple[list[Any], list[Any], list[str]]:
    """Split MCP tools into portfolio, research, and leftover names."""
    portfolio: list[Any] = []
    research: list[Any] = []
    other: list[str] = []
    for tool in tools:
        name = getattr(tool, "name", None) or ""
        if name in PORTFOLIO_TOOL_NAMES:
            portfolio.append(tool)
        elif name in RESEARCH_TOOL_NAMES:
            research.append(tool)
        else:
            other.append(name or type(tool).__name__)
    return portfolio, research, other


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


def _wrap_specialist(agent_name: str, subgraph: Any):
    """Run a specialist subgraph and log agent_name without leaking prompts."""

    async def _node(state: GraphState, config: RunnableConfig) -> dict:
        started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "agent.run.started",
            f"{agent_name} specialist started",
            agent_name=agent_name,
        )
        try:
            result = await subgraph.ainvoke({"messages": state["messages"]}, config)
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
        return {"messages": result["messages"]}

    return _node


def compile_supervisor_graph(model: Any, tools: Sequence[Any]):
    """Build the parent StateGraph: supervisor + portfolio + research."""
    portfolio_tools, research_tools, other = partition_mcp_tools(tools)
    if other:
        log_event(
            logger,
            logging.WARNING,
            "agent.build.unexpected_tools",
            "Unexpected MCP tools were not assigned to a specialist",
            tool_count=len(other),
            argument_keys=sorted(other),
        )

    portfolio_agent = create_agent(
        model,
        portfolio_tools,
        system_prompt=PORTFOLIO_PROMPT,
        name="portfolio",
    )
    research_agent = create_agent(
        model,
        research_tools,
        system_prompt=RESEARCH_PROMPT,
        name="research",
    )
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

    workflow = StateGraph(GraphState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("portfolio", _wrap_specialist("portfolio", portfolio_agent))
    workflow.add_node("research", _wrap_specialist("research", research_agent))
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("portfolio", "supervisor")
    workflow.add_edge("research", "supervisor")
    return workflow.compile()
