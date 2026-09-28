"""Portfolio A2A process: AgentApp, Nacos registration, apira-mcp tools only."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from agents.a2a.specialist_app import create_specialist_app
from agents.llm_mcp import create_mcp_client_and_model
from logging_config import configure_logging

load_dotenv()
configure_logging()

os.environ.setdefault("PORT", "8110")
os.environ.setdefault("A2A_HOST", "portfolio")


def _skills():
    from a2a.types import AgentSkill

    return [
        AgentSkill(
            id="login",
            name="login",
            description="Authenticate a user.",
            tags=["portfolio", "login"],
        ),
        AgentSkill(
            id="get_portfolio",
            name="get_portfolio",
            description="Fetch holdings for a user.",
            tags=["portfolio"],
        ),
    ]


async def load_specialist():
    from agents.portfolio_sub_agent.agent import build_agent as build_portfolio

    model, client = await create_mcp_client_and_model(mcp_servers=["apira"])
    return await build_portfolio(model, client)


app = create_specialist_app(
    role="portfolio",
    description="Login and retrieve portfolio holdings.",
    skills=_skills(),
    load_specialist=load_specialist,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8110")),
        access_log=False,
    )
