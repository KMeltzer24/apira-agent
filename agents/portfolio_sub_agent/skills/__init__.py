"""Skills for the portfolio sub-agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from agents.portfolio_sub_agent.mcp_tools import TOOL_NAMES
from agents.skills_runtime import load_prompt_skills, make_shell_skill_tool

SKILLS_DIR = Path(__file__).resolve().parent

_TOOL_ORDER = ("login", "get_portfolio")


def load_prompt_skill_text() -> str:
    """NL-only skills for system-prompt injection."""
    return load_prompt_skills(SKILLS_DIR, _TOOL_ORDER)


def _service_env() -> dict[str, str]:
    import os

    return {
        "USER_SERVICE_URL": os.environ.get(
            "USER_SERVICE_URL", "http://host.docker.internal:8001"
        ),
        "PORTFOLIO_SERVICE_URL": os.environ.get(
            "PORTFOLIO_SERVICE_URL", "http://host.docker.internal:8002"
        ),
    }


def load_shell_tools() -> list[Any]:
    """Tools that execute embedded bash from ``*_shell.md``."""
    login = make_shell_skill_tool(
        tool_name="login",
        skills_dir=SKILLS_DIR,
        description="Authenticate a user and return user_id.",
        arg_fields={
            "username": (str, Field(..., description="Username")),
            "password": (str, Field(..., description="Password")),
        },
        extra_env=_service_env,
    )
    get_portfolio = make_shell_skill_tool(
        tool_name="get_portfolio",
        skills_dir=SKILLS_DIR,
        description="Return portfolio holdings for a user_id.",
        arg_fields={
            "user_id": (int, Field(..., description="User id from login")),
        },
        extra_env=_service_env,
    )
    assert {login.name, get_portfolio.name} == set(TOOL_NAMES)
    return [login, get_portfolio]
