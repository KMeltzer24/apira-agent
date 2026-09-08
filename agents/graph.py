"""Parent StateGraph: wires supervisor + specialists. No tool allowlists here."""

from __future__ import annotations

from typing import Any, Sequence

from langgraph.graph import START, StateGraph

from agents.portfolio_sub_agent.agent import build_agent as build_portfolio_agent
from agents.research_sub_agent.agent import build_agent as build_research_agent
from agents.state import GraphState
from agents.supervisor.agent import build_node as build_supervisor_node
from agents.supervisor.agent import reset_supervisor_hops

__all__ = ["compile_supervisor_graph", "reset_supervisor_hops", "GraphState"]


async def compile_supervisor_graph(model: Any, client: Any):
    """Build the parent StateGraph: supervisor + portfolio + research.

    Sub-agents load their own MCP tool allowlists via the shared client.
    Tool names are not referenced in this module.
    """
    all_tools: Sequence[Any] = await client.get_tools()
    portfolio_node = await build_portfolio_agent(model, client, tools=all_tools)
    research_node = await build_research_agent(model, client, tools=all_tools)
    supervisor_node = build_supervisor_node(model)

    workflow = StateGraph(GraphState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("portfolio", portfolio_node)
    workflow.add_node("research", research_node)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("portfolio", "supervisor")
    workflow.add_edge("research", "supervisor")
    return workflow.compile()
