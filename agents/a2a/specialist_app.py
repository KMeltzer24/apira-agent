"""AgentScope AgentApp factory for one A2A specialist process."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.messages import AIMessage

from agents.a2a.payload import decode_state, encode_state, message_text
from agents.llm_errors import user_facing_llm_error
from agentscope_runtime.engine.app import AgentApp
from agentscope_runtime.engine.deployers.adapter.a2a import AgentCardWithRuntimeConfig
from logging_config import (
    REQUEST_ID_HEADER,
    log_event,
    normalize_request_id,
    reset_request_id,
    set_request_id,
)

logger = logging.getLogger(__name__)

SpecialistLoader = Callable[[], Awaitable[Any]]


def create_specialist_app(
    *,
    role: str,
    description: str,
    skills: list,
    load_specialist: SpecialistLoader,
) -> AgentApp:
    host = os.environ.get("A2A_HOST", role)
    port = int(os.environ.get("PORT", "8110"))
    os.environ.setdefault("PORT", str(port))

    @asynccontextmanager
    async def lifespan(app):
        app.state.specialist = None
        app.state.specialist_lock = asyncio.Lock()
        yield

    app = AgentApp(
        app_name=role,
        app_description=description,
        lifespan=lifespan,
        a2a_config=AgentCardWithRuntimeConfig(
            agent_card={
                "name": role,
                "description": description,
                "url": f"http://{host}:{port}/a2a",
                "version": "1.0.0",
                "skills": skills,
            },
            host=host,
            port=port,
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
                    app.state.specialist = await load_specialist()
        return app.state.specialist

    @app.query(framework="langgraph")
    async def query_func(self, msgs=None, request=None, **kwargs):
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
        try:
            result = await specialist(
                state, config={"metadata": {"request_id": inbound_request_id}}
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "agent.run.failed",
                f"{role} specialist failed",
                agent_name=role,
                error_type=type(exc).__name__,
            )
            result = {
                **state,
                "messages": list(state.get("messages") or [])
                + [AIMessage(content=user_facing_llm_error(exc))],
            }
        encoded = encode_state(result)
        if token is not None:
            reset_request_id(token)
        yield AIMessage(id=f"{role}-result", content=encoded), True

    return app
