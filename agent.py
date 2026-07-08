"""Apira agent — a LangGraph agent that uses the Apira MCP tools.

It connects to the apira-mcp server, loads the `login` and `get_portfolio`
tools, and runs a user prompt through the Gemini API. The agent decides on its
own to log in first, then fetch the portfolio.

Run directly (`python agent.py`) for a one-shot demo with a hard-coded prompt,
or import `build_agent` / `run_agent` to serve it (see server.py).
"""

import asyncio
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

# Always set via .env / docker-compose. This fallback matches the in-container
# EC2 deployment (the agent container reaches the MCP container's published port).
MCP_URL = os.environ.get("MCP_URL", "http://host.docker.internal:8000/mcp")

# Gemini model that drives the agent (needs GOOGLE_API_KEY in the environment).
GEMINI_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-flash-lite")

# Default prompt used by the one-shot CLI demo. The agent must work out that it
# needs to call `login` to get a user_id, then `get_portfolio`.
DEFAULT_PROMPT = (
    "Log in as user 'alice' with password 'password', then retrieve that "
    "user's portfolio and summarize the holdings."
)

SYSTEM_PROMPT = (
    "You are a portfolio assistant for the Apira system. "
    "You have tools to log in a user, fetch a portfolio, and search stock research "
    "files on the server via searchLocalFolder. "
    "To get a portfolio you first need the user_id returned by the login tool. "
    "Always log in first, then call get_portfolio with that user_id. "
    "Report the holdings clearly to the user. "
    "For stock recommendations: after fetching the portfolio, call searchLocalFolder "
    "with each holding's ticker symbol. Format each holding as: ticker and action "
    "(Hold/Add/Trim), then cited filenames, then one or two short sentences of reasoning. "
    "Be concise — no sector overview, no holdings summary list."
)


async def build_agent():
    """Load MCP tools and build a LangGraph agent backed by Gemini."""
    client = MultiServerMCPClient(
        {
            "apira": {
                "url": MCP_URL,
                "transport": "streamable_http",
            }
        }
    )
    tools = await client.get_tools()
    # max_retries=0 so a 429 (quota) fails fast instead of honoring Gemini's
    # multi-second retry delay and hanging the request.
    model = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL, temperature=0, max_retries=0
    )
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT)


def _as_text(content) -> str:
    """Normalize a message's content to plain text.

    Gemini returns the final content as a list of blocks like
    [{"type": "text", "text": "..."}]; join the text parts into one string.
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
