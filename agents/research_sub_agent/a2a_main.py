"""Research A2A process: AgentApp, Nacos registration, rag MCP tools only."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from agents.a2a.specialist_app import create_specialist_app
from agents.llm_mcp import create_mcp_client_and_model
from logging_config import configure_logging

load_dotenv()
configure_logging()

os.environ.setdefault("PORT", "8120")
os.environ.setdefault("A2A_HOST", "research")


def _skills():
    from a2a.types import AgentSkill

    return [
        AgentSkill(
            id="searchLocalFolder",
            name="searchLocalFolder",
            description="Search the local stock-research folder.",
            tags=["research"],
        ),
        AgentSkill(
            id="searchVectorDB",
            name="searchVectorDB",
            description="Search the vector research database.",
            tags=["research"],
        ),
    ]


async def load_specialist():
    from agents.research_sub_agent.agent import build_agent as build_research

    model, client = await create_mcp_client_and_model(mcp_servers=["research"])
    return await build_research(model, client)


app = create_specialist_app(
    role="research",
    description="Search local folder and vector research for stock recommendations.",
    skills=_skills(),
    load_specialist=load_specialist,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8120")),
        access_log=False,
    )
