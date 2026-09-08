"""Shared LangGraph state for the supervisor parent graph."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
