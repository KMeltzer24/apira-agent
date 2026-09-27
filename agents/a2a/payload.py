"""JSON envelope for GraphState over A2A text messages."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import convert_to_messages, message_to_dict, messages_from_dict

from logging_config import get_request_id

STATE_PREFIX = "APIRA_STATE_V1:"


def encode_state(state: dict[str, Any]) -> str:
    """Serialize LangGraph specialist state into one A2A text payload."""
    messages = convert_to_messages(list(state.get("messages") or []))
    body = {
        "messages": [message_to_dict(message) for message in messages],
        "logged_in": state.get("logged_in"),
        "user_id": state.get("user_id"),
        "request_id": get_request_id(),
    }
    return STATE_PREFIX + json.dumps(body)


def decode_state(text: str) -> dict[str, Any]:
    """Parse an A2A text payload back into GraphState fields."""
    raw = (text or "").strip()
    if not raw.startswith(STATE_PREFIX):
        return {"messages": convert_to_messages([{"role": "user", "content": raw}])}
    data = json.loads(raw[len(STATE_PREFIX) :])
    if not isinstance(data, dict):
        raise ValueError("A2A state payload must be a JSON object")
    messages = messages_from_dict(data.get("messages") or [])
    result: dict[str, Any] = {"messages": messages}
    if data.get("logged_in") is not None:
        result["logged_in"] = bool(data["logged_in"])
    if data.get("user_id") is not None:
        result["user_id"] = int(data["user_id"])
    if data.get("request_id"):
        result["request_id"] = str(data["request_id"])
    return result


def message_text(message: Any) -> str:
    """Best-effort plain text from a LangChain or dict message."""
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content or "")
