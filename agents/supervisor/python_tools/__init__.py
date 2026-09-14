"""In-process last-recommendation REST helpers and the GET python tool."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from langchain_core.tools import tool

from logging_config import REQUEST_ID_HEADER, get_request_id


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    request_id = get_request_id()
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    return headers


def _base_url() -> str:
    return os.environ.get(
        "PORTFOLIO_SERVICE_URL", "http://host.docker.internal:8002"
    ).rstrip("/")


async def fetch_previous_recommendation(user_id: int) -> str:
    """GET the last recommendation body, or a short empty message."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{_base_url()}/recommendation",
            params={"user_id": user_id},
            headers=_headers(),
        )
        response.raise_for_status()
        payload = response.json()
    body = payload.get("body") if isinstance(payload, dict) else None
    if not body:
        return "No previous recommendation is stored for this user."
    return str(body)


async def save_recommendation(user_id: int, body: str) -> str:
    """PUT the last recommendation (replaces any previous row)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{_base_url()}/recommendation",
            json={"user_id": user_id, "body": body},
            headers=_headers(),
        )
        response.raise_for_status()
        return json.dumps(response.json())


@tool
async def getPreviousRecommendation(user_id: int) -> str:
    """Return the last saved recommendation for a user_id."""
    return await fetch_previous_recommendation(user_id)


def load_tools() -> list[Any]:
    """Supervisor python tools (read-only)."""
    return [getPreviousRecommendation]
