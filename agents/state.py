"""Shared LangGraph state for the supervisor parent graph."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired, TypedDict


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # Set True after the portfolio specialist runs (login + holdings).
    logged_in: NotRequired[bool]
    user_id: NotRequired[int]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content or "")


def extract_user_id(messages: list[Any] | None, fallback: int | None = None) -> int | None:
    """Find user_id from login / get_portfolio tool traffic, else *fallback*."""
    if fallback is not None:
        try:
            return int(fallback)
        except (TypeError, ValueError):
            pass
    for message in reversed(list(messages or [])):
        name = getattr(message, "name", None)
        if isinstance(message, dict):
            name = message.get("name", name)
            content = message.get("content", "")
        else:
            content = getattr(message, "content", "")
        text = _content_text(content)
        if name in {"login", "get_portfolio", "getPreviousRecommendation"}:
            try:
                payload = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and payload.get("user_id") is not None:
                try:
                    return int(payload["user_id"])
                except (TypeError, ValueError):
                    pass
        for tool_call in getattr(message, "tool_calls", None) or []:
            tool_name = (
                tool_call.get("name")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "name", None)
            )
            args = (
                tool_call.get("args")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "args", None)
            ) or {}
            if tool_name in {"get_portfolio", "getPreviousRecommendation"} and "user_id" in args:
                try:
                    return int(args["user_id"])
                except (TypeError, ValueError):
                    continue
    return None


def last_ai_text(messages: list[Any] | None) -> str:
    """Last assistant/AI message text (for saving a recommendation)."""
    for message in reversed(list(messages or [])):
        msg_type = getattr(message, "type", None)
        if isinstance(message, dict):
            role = str(message.get("role", "")).lower()
            if role in {"assistant", "ai"}:
                return _content_text(message.get("content", "")).strip()
            continue
        if msg_type == "ai":
            return _content_text(getattr(message, "content", "")).strip()
    return ""
