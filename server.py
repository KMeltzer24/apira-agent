"""HTTP wrapper around the Apira agent.

Exposes a single `POST /chat` endpoint so a frontend can send a user message
and get the agent's reply. The agent is built lazily on the first request and
cached, so the server boots instantly and tolerates the MCP server or Ollama
not being ready at startup.

Run with:  uvicorn server:app --host 0.0.0.0 --port 8100
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import build_agent, run_agent

# Comma-separated list of allowed browser origins for the frontend.
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")


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
)


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
    agent = await get_agent(app)
    reply = await run_agent(agent, req.message)
    return ChatResponse(reply=reply)
