"""A2A specialist server (portfolio or research) using AgentScope AgentApp.

Each container registers its Agent Card with Nacos and runs the existing
LangChain specialist. The supervisor discovers the card and calls it over A2A.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from agent import create_mcp_client_and_model
from agents.a2a.payload import decode_state, encode_state, message_text
from agentscope_runtime.engine.app import AgentApp
from agentscope_runtime.engine.deployers.adapter.a2a import AgentCardWithRuntimeConfig
from logging_config import (
    REQUEST_ID_HEADER,
    configure_logging,
    log_event,
    normalize_request_id,
    reset_request_id,
    set_request_id,
)

load_dotenv()
configure_logging()
logger = logging.getLogger(__name__)

ROLE = os.environ.get("AGENT_ROLE", "").strip().lower()
if ROLE not in {"portfolio", "research"}:
    raise SystemExit(
        "a2a_server.py requires AGENT_ROLE=portfolio or AGENT_ROLE=research"
    )

A2A_HOST = os.environ.get("A2A_HOST", ROLE)
PORT = int(os.environ.get("PORT", "8110" if ROLE == "portfolio" else "8120"))
os.environ.setdefault("PORT", str(PORT))

_DESCRIPTIONS = {
    "portfolio": "Login and retrieve portfolio holdings.",
    "research": "Search local folder and vector research for stock recommendations.",
}


def _skills():
    from a2a.types import AgentSkill

    if ROLE == "portfolio":
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


@asynccontextmanager
async def lifespan(app):
    app.state.specialist = None
    app.state.specialist_lock = asyncio.Lock()
    yield


app = AgentApp(
    app_name=ROLE,
    app_description=_DESCRIPTIONS[ROLE],
    lifespan=lifespan,
    a2a_config=AgentCardWithRuntimeConfig(
        agent_card={
            "name": ROLE,
            "description": _DESCRIPTIONS[ROLE],
            "url": f"http://{A2A_HOST}:{PORT}/a2a",
            "version": "1.0.0",
            "skills": _skills(),
        },
        host=A2A_HOST,
        port=PORT,
        task_timeout=int(os.environ.get("A2A_TASK_TIMEOUT", "180")),
    ),
)


@app.middleware("http")
async def request_context(request, call_next):
    request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = set_request_id(request_id)
    started = time.perf_counter()
    path = request.url.path
    http_level = logging.DEBUG if path == "/health" else logging.INFO
    log_event(
        logger,
        http_level,
        "http.request.started",
        f"HTTP {request.method} {path} started",
        method=request.method,
        path=path,
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "http.request.failed",
            f"HTTP {request.method} {path} failed ({type(exc).__name__})",
            method=request.method,
            path=path,
            error_type=type(exc).__name__,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        raise
    response.headers[REQUEST_ID_HEADER] = request_id
    log_event(
        logger,
        http_level,
        "http.request.completed",
        f"HTTP {request.method} {path} completed ({response.status_code})",
        method=request.method,
        path=path,
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    reset_request_id(token)
    return response


async def get_specialist():
    if not hasattr(app.state, "specialist_lock"):
        app.state.specialist = None
        app.state.specialist_lock = asyncio.Lock()
    if app.state.specialist is None:
        async with app.state.specialist_lock:
            if app.state.specialist is None:
                model, client = await create_mcp_client_and_model()
                if ROLE == "portfolio":
                    from agents.portfolio_sub_agent.agent import (
                        build_agent as build_portfolio,
                    )

                    app.state.specialist = await build_portfolio(model, client)
                else:
                    from agents.research_sub_agent.agent import (
                        build_agent as build_research,
                    )

                    app.state.specialist = await build_research(model, client)
    return app.state.specialist


@app.query(framework="langgraph")
async def query_func(self, msgs=None, request=None, **kwargs):
    """Run the LangChain specialist and yield one assistant message."""
    incoming = msgs
    if isinstance(incoming, list):
        last = incoming[-1] if incoming else None
    else:
        last = incoming
    payload_text = message_text(last)
    state = decode_state(payload_text)
    inbound_request_id = state.pop("request_id", None)
    token = None
    if inbound_request_id:
        token = set_request_id(inbound_request_id)
    specialist = await get_specialist()
    result = await specialist(state, config={"metadata": {"request_id": inbound_request_id}})
    encoded = encode_state(result)
    if token is not None:
        reset_request_id(token)
    # AgentScope's LangGraph stream adapter skips Message() when msg.id is
    # None (same as its initial msg_id), then crashes on last=True.
    yield AIMessage(id=f"{ROLE}-result", content=encoded), True


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT, access_log=False)
