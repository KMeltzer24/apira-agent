"""Supervisor-side A2A caller.

AgentScope 2.0.8's ``A2AAgent`` imports ``TransportProtocol`` from
``a2a.utils.constants`` (a2a-sdk 1.x). AgentScope Runtime pins a2a-sdk 0.3.x,
where that symbol lives on ``a2a.types``. The official 0.3 ``ClientFactory``
is the same SDK the specialist ``AgentApp`` servers use.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.client.helpers import create_text_message_object
from a2a.types import Message, Role, Task, TransportProtocol
from a2a.utils.message import get_message_text
from a2a.utils.parts import get_text_parts

from agents.a2a.discover import discover_agent_card
from agents.a2a.payload import decode_state, encode_state
from logging_config import log_event

logger = logging.getLogger(__name__)

_cards: dict[str, Any] = {}


async def _agent_card(agent_name: str):
    card = _cards.get(agent_name)
    if card is None:
        card = await discover_agent_card(agent_name)
        _cards[agent_name] = card
    return card


def _text_from_event(event: Any) -> str:
    if isinstance(event, Message):
        return get_message_text(event)
    task = event[0] if isinstance(event, tuple) and event else event
    if not isinstance(task, Task):
        return ""
    chunks: list[str] = []
    for artifact in task.artifacts or []:
        chunks.extend(get_text_parts(artifact.parts or []))
    if chunks:
        return "\n".join(chunks)
    status_message = getattr(task.status, "message", None)
    if isinstance(status_message, Message):
        return get_message_text(status_message)
    return ""


async def call_specialist(agent_name: str, state: dict[str, Any]) -> dict[str, Any]:
    """Send GraphState to a remote specialist and return the updated state."""
    card = await _agent_card(agent_name)
    timeout = httpx.Timeout(float(os.environ.get("A2A_TASK_TIMEOUT", "180")))
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        a2a_client = ClientFactory(
            ClientConfig(
                streaming=False,
                polling=False,
                httpx_client=http_client,
                supported_transports=[TransportProtocol.jsonrpc],
            )
        ).create(card)
        request = create_text_message_object(
            role=Role.user,
            content=encode_state(state),
        )
        text = ""
        async for event in a2a_client.send_message(request):
            extracted = _text_from_event(event)
            if extracted:
                text = extracted
    decoded = decode_state(text)
    log_event(
        logger,
        logging.INFO,
        "a2a.call.completed",
        f"A2A call to {agent_name} completed",
        agent_name=agent_name,
    )
    return decoded
