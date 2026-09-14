"""Parent StateGraph: sequential supervisor → portfolio → logged_in → research."""

from __future__ import annotations

from typing import Any, Sequence

from langgraph.graph import END, START, StateGraph

from agents.portfolio_sub_agent.agent import build_agent as build_portfolio_agent
from agents.research_sub_agent.agent import build_agent as build_research_agent
from agents.state import GraphState
from agents.supervisor.agent import build_node as build_supervisor_node
from agents.supervisor.agent import reset_supervisor_hops
from agents.supervisor.mcp_tools import load_tools as load_supervisor_mcp_tools
from agents.supervisor.mcp_tools import select_tools as select_supervisor_tools
from agents.supervisor.save_recommendation import (
    build_save_node as build_save_recommendation_node,
)
from agents.supervisor.python_tools import load_tools as load_supervisor_python_tools
from agents.supervisor.skills import (
    load_prompt_tools as load_supervisor_prompt_tools,
    load_shell_tools as load_supervisor_shell_tools,
)
from agents.tool_mode import (
    TOOL_MODE_MCP,
    TOOL_MODE_PYTHON,
    TOOL_MODE_SKILLS_PROMPT,
    TOOL_MODE_SKILLS_SHELL,
    get_tool_mode,
)

__all__ = ["compile_supervisor_graph", "reset_supervisor_hops", "GraphState"]


async def _load_supervisor_read_tools(
    model: Any, client: Any, all_tools: Sequence[Any], mode: str
) -> list[Any]:
    """getPreviousRecommendation for the logged-in supervisor only."""
    if mode == TOOL_MODE_MCP:
        if all_tools:
            return select_supervisor_tools(all_tools)
        return await load_supervisor_mcp_tools(client)
    if mode == TOOL_MODE_PYTHON:
        return load_supervisor_python_tools()
    if mode == TOOL_MODE_SKILLS_PROMPT:
        return load_supervisor_prompt_tools(model)
    if mode == TOOL_MODE_SKILLS_SHELL:
        return load_supervisor_shell_tools(model)
    return []


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
    read_tools = await _load_supervisor_read_tools(model, client, all_tools, mode)
    supervisor_node = build_supervisor_node(model, logged_in=False)
    logged_in_node = build_supervisor_node(
        model, logged_in=True, tools=read_tools
    )
    save_recommendation_node = build_save_recommendation_node()

    workflow = StateGraph(GraphState)
    workflow.add_node("supervisor", supervisor_node, destinations=("portfolio", END))
    workflow.add_node("portfolio", portfolio_node)
    workflow.add_node(
        "logged_in",
        logged_in_node,
        destinations=("research", "portfolio", END),
    )
    workflow.add_node("research", research_node)
    workflow.add_node("save_recommendation", save_recommendation_node)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("portfolio", "logged_in")
    workflow.add_edge("research", "save_recommendation")
    workflow.add_edge("save_recommendation", "logged_in")
    return workflow.compile()
