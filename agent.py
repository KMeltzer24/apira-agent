"""Apira agent — a LangGraph agent that uses the Apira MCP tools.

It connects to the apira-mcp server, loads the `login` and `get_portfolio`
tools, and runs a user prompt through a local Ollama model. The agent decides
on its own to log in first, then fetch the portfolio.

Run directly (`python agent.py`) for a one-shot demo with a hard-coded prompt,
or import `build_agent` / `run_agent` to serve it (see server.py).
"""

import asyncio
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8000/mcp")

# Which LLM backs the agent: "ollama" (local) or "google_genai" (Gemini API).
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")

# Used when LLM_PROVIDER=ollama (local model on your Mac).
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Used when LLM_PROVIDER=google_genai (needs GOOGLE_API_KEY in the environment).
GEMINI_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

# Default prompt used by the one-shot CLI demo. The agent must work out that it
# needs to call `login` to get a user_id, then `get_portfolio`.
DEFAULT_PROMPT = (
    "Log in as user 'alice' with password 'password', then retrieve that "
    "user's portfolio and summarize the holdings."
)

SYSTEM_PROMPT = (
    "You are a portfolio assistant for the Apira system. "
    "You have tools to log in a user and to fetch a portfolio. "
    "To get a portfolio you first need the user_id returned by the login tool. "
    "Always log in first, then call get_portfolio with that user_id. "
    "Report the holdings clearly to the user."
)


def make_model():
    """Build the chat model for the configured provider (imports lazily)."""
    if LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0
        )
    if LLM_PROVIDER == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0)
    raise ValueError(
        f"Unknown LLM_PROVIDER={LLM_PROVIDER!r} (use 'ollama' or 'google_genai')"
    )


async def build_agent():
    """Load MCP tools and build a LangGraph agent backed by the chosen model."""
    client = MultiServerMCPClient(
        {
            "apira": {
                "url": MCP_URL,
                "transport": "streamable_http",
            }
        }
    )
    tools = await client.get_tools()
    return create_agent(make_model(), tools, system_prompt=SYSTEM_PROMPT)


def _as_text(content) -> str:
    """Normalize a message's content to plain text.

    Ollama returns a string; Gemini returns a list of content blocks like
    [{"type": "text", "text": "..."}]. Join the text parts in either case.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


async def run_agent(agent, prompt: str) -> str:
    """Run one user prompt through the agent and return the final text answer."""
    result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    return _as_text(result["messages"][-1].content)


async def main() -> None:
    agent = await build_agent()
    print(f"User prompt: {DEFAULT_PROMPT}\n")
    print("Running agent...\n")
    answer = await run_agent(agent, DEFAULT_PROMPT)
    print("=== Agent answer ===")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
