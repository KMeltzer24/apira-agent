"""Skills for the supervisor (getPreviousRecommendation only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import Field

from agents.skills_runtime import make_codegen_skill_tool
from agents.supervisor.mcp_tools import TOOL_NAMES

SKILLS_DIR = Path(__file__).resolve().parent


def _service_env() -> dict[str, str]:
    return {
        "PORTFOLIO_SERVICE_URL": os.environ.get(
            "PORTFOLIO_SERVICE_URL", "http://host.docker.internal:8002"
        ),
    }


def _build_tools(model: Any, *, kind: str) -> list[Any]:
    get_prev = make_codegen_skill_tool(
        model=model,
        tool_name="getPreviousRecommendation",
        skills_dir=SKILLS_DIR,
        description="Return the last saved recommendation for a user_id.",
        arg_fields={
            "user_id": (int, Field(..., description="User id from login")),
        },
        kind=kind,  # type: ignore[arg-type]
        extra_env=_service_env,
    )
    assert {get_prev.name} == set(TOOL_NAMES)
    return [get_prev]


def load_prompt_tools(model: Any) -> list[Any]:
    return _build_tools(model, kind="prompt")


def load_shell_tools(model: Any) -> list[Any]:
    return _build_tools(model, kind="shell")
