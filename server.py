"""HTTP wrapper around the Apira agent.

Exposes a single `POST /chat` endpoint so a frontend can send a user message
and get the agent's reply. The agent is built lazily on the first request and
cached, so the server boots instantly and tolerates the MCP server not being
ready at startup.

Run with:  uvicorn server:app --host 0.0.0.0 --port 8100
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import build_agent, run_agent
from logging_config import (
    REQUEST_ID_HEADER,
    log_event,
    normalize_request_id,
    reset_request_id,
    set_request_id,
)

# Comma-separated list of allowed browser origins for the frontend.
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = None
    app.state.agent_lock = asyncio.Lock()
    yield


app = FastAPI(title="Apira Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Correlate each request and emit content-free HTTP lifecycle logs."""
    request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = set_request_id(request_id)
    started = time.perf_counter()
    fields = {"method": request.method, "path": request.url.path}
    log_event(
        logger,
        logging.INFO,
        "http.request.started",
        "HTTP request started",
        **fields,
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "http.request.failed",
            "HTTP request failed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
            **fields,
        )
        raise
    else:
        response.headers[REQUEST_ID_HEADER] = request_id
        log_event(
            logger,
            logging.INFO,
            "http.request.completed",
            "HTTP request completed",
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            **fields,
        )
        return response
    finally:
        reset_request_id(token)


async def get_agent(app: FastAPI):
    """Build the agent on first use and cache it for subsequent requests."""
    if app.state.agent is None:
        async with app.state.agent_lock:
            if app.state.agent is None:
                app.state.agent = await build_agent()
    return app.state.agent


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    started = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "chat.started",
        "Chat request started",
        message_length=len(req.message),
    )
    try:
        agent = await get_agent(app)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat.failed",
            "Chat request failed",
            message_length=len(req.message),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        raise
    try:
        reply = await run_agent(agent, req.message)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat.failed",
            "Chat request failed",
            message_length=len(req.message),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        # Return a readable message (with CORS headers intact) instead of a bare
        # 500, which the browser would surface only as "Failed to fetch".
        detail = str(exc)
        if "RESOURCE_EXHAUSTED" in detail or "429" in detail:
            reply = (
                "The Gemini API quota is exhausted for now. Try again later, "
                "switch LLM_MODEL, or raise the project's quota."
            )
        else:
            reply = f"The agent hit an error: {detail[:300]}"
    else:
        log_event(
            logger,
            logging.INFO,
            "chat.completed",
            "Chat request completed",
            message_length=len(req.message),
            reply_length=len(reply),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    return ChatResponse(reply=reply)
