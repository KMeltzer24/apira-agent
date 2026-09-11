"""In-process LangChain @tool implementations for the portfolio specialist."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from langchain_core.tools import tool

from logging_config import REQUEST_ID_HEADER, get_request_id

USER_SERVICE_URL = os.environ.get(
    "USER_SERVICE_URL", "http://host.docker.internal:8001"
)
PORTFOLIO_SERVICE_URL = os.environ.get(
    "PORTFOLIO_SERVICE_URL", "http://host.docker.internal:8002"
)


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    request_id = get_request_id()
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    return headers


@tool
async def login(username: str, password: str) -> str:
    """Authenticate a user and return user_id."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{USER_SERVICE_URL.rstrip('/')}/login",
            json={"username": username, "password": password},
            headers=_headers(),
        )
        response.raise_for_status()
        return json.dumps(response.json())


@tool
async def get_portfolio(user_id: int) -> str:
    """Return portfolio holdings for a user_id."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{PORTFOLIO_SERVICE_URL.rstrip('/')}/portfolio",
            params={"user_id": user_id},
            headers=_headers(),
        )
        response.raise_for_status()
        return json.dumps(response.json())


def load_tools() -> list[Any]:
    """Return portfolio python tools in a stable order."""
    return [login, get_portfolio]
