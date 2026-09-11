"""Skills for the portfolio sub-agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from agents.portfolio_sub_agent.mcp_tools import TOOL_NAMES
from agents.skills_runtime import make_codegen_skill_tool

SKILLS_DIR = Path(__file__).resolve().parent


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


def _build_tools(model: Any, *, kind: str) -> list[Any]:
    login = make_codegen_skill_tool(
        model=model,
        tool_name="login",
        skills_dir=SKILLS_DIR,
        description="Authenticate a user and return user_id.",
        arg_fields={
            "username": (str, Field(..., description="Username")),
            "password": (str, Field(..., description="Password")),
        },
        kind=kind,  # type: ignore[arg-type]
        extra_env=_service_env,
    )
    get_portfolio = make_codegen_skill_tool(
        model=model,
        tool_name="get_portfolio",
        skills_dir=SKILLS_DIR,
        description="Return portfolio holdings for a user_id.",
        arg_fields={
            "user_id": (int, Field(..., description="User id from login")),
        },
        kind=kind,  # type: ignore[arg-type]
        extra_env=_service_env,
    )
    assert {login.name, get_portfolio.name} == set(TOOL_NAMES)
    return [login, get_portfolio]


def load_prompt_tools(model: Any) -> list[Any]:
    """Codegen tools driven by NL ``<tool>.md`` skills."""
    return _build_tools(model, kind="prompt")


def load_shell_tools(model: Any) -> list[Any]:
    """Codegen tools driven by ``*_shell.md`` (sample bash is a hint)."""
    return _build_tools(model, kind="shell")
