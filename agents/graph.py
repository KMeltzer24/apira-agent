"""Parent StateGraph: sequential supervisor → portfolio → logged_in → research."""

from __future__ import annotations

from typing import Any, Sequence

from langgraph.graph import END, START, StateGraph

from agents.portfolio_sub_agent.agent import build_agent as build_portfolio_agent
from agents.research_sub_agent.agent import build_agent as build_research_agent
from agents.state import GraphState
from agents.supervisor.agent import build_node as build_supervisor_node
from agents.supervisor.agent import reset_supervisor_hops
from agents.tool_mode import TOOL_MODE_MCP, get_tool_mode

__all__ = ["compile_supervisor_graph", "reset_supervisor_hops", "GraphState"]


async def compile_supervisor_graph(model: Any, client: Any):
    """Build the parent StateGraph: guest supervisor, then logged-in supervisor.

    Research is not reachable until portfolio has run. Sub-agents load tools
    according to ``TOOL_MODE``. MCP tool names are not referenced in this module.
    """
    mode = get_tool_mode()
    all_tools: Sequence[Any] = (
        await client.get_tools() if mode == TOOL_MODE_MCP else []
    )
    portfolio_node = await build_portfolio_agent(model, client, tools=all_tools)
    research_node = await build_research_agent(model, client, tools=all_tools)
    supervisor_node = build_supervisor_node(model, logged_in=False)
    logged_in_node = build_supervisor_node(model, logged_in=True)

    workflow = StateGraph(GraphState)
    workflow.add_node("supervisor", supervisor_node, destinations=("portfolio", END))
    workflow.add_node("portfolio", portfolio_node)
    workflow.add_node("logged_in", logged_in_node, destinations=("research", END))
    workflow.add_node("research", research_node)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("portfolio", "logged_in")
    workflow.add_edge("research", "logged_in")
    return workflow.compile()
