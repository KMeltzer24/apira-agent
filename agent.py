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
from langchain_ollama import ChatOllama

load_dotenv()

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8000/mcp")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

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


async def build_agent():
    """Load MCP tools and build a LangGraph agent backed by the local model."""
    client = MultiServerMCPClient(
        {
            "apira": {
                "url": MCP_URL,
                "transport": "streamable_http",
            }
        }
    )
    tools = await client.get_tools()
    model = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT)


async def run_agent(agent, prompt: str) -> str:
    """Run one user prompt through the agent and return the final text answer."""
    result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    return result["messages"][-1].content


async def main() -> None:
    agent = await build_agent()
    print(f"User prompt: {DEFAULT_PROMPT}\n")
    print("Running agent...\n")
    answer = await run_agent(agent, DEFAULT_PROMPT)
    print("=== Agent answer ===")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
