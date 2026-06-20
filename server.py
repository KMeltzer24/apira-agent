"""HTTP wrapper around the Apira agent.

Exposes a single `POST /chat` endpoint so a frontend can send a user message
and get the agent's reply. The agent is built once at startup and reused.

Run with:  uvicorn server:app --reload --port 8100
"""

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
    app.state.agent = await build_agent()
    yield


app = FastAPI(title="Apira Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    reply = await run_agent(app.state.agent, req.message)
    return ChatResponse(reply=reply)
