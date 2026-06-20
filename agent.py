"""Apira agent — a standalone LangGraph agent that uses the Apira MCP tools.

It connects to the apira-mcp server, loads the `login` and `get_portfolio`
tools, and runs a hard-coded user prompt through a local Ollama model. The
agent decides on its own to log in first, then fetch the portfolio.
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

# Hard-coded user prompt (per project requirement). The agent must work out
# that it needs to call `login` to get a user_id, then `get_portfolio`.
USER_PROMPT = (
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


async def main() -> None:
    client = MultiServerMCPClient(
        {
            "apira": {
                "url": MCP_URL,
                "transport": "streamable_http",
            }
        }
    )

    tools = await client.get_tools()
    print(f"Loaded {len(tools)} MCP tools: {', '.join(t.name for t in tools)}")

    model = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)
    agent = create_agent(model, tools, system_prompt=SYSTEM_PROMPT)

    print(f"\nUser prompt: {USER_PROMPT}\n")
    print("Running agent...\n")

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": USER_PROMPT}]}
    )

    final_message = result["messages"][-1]
    print("=== Agent answer ===")
    print(final_message.content)


if __name__ == "__main__":
    asyncio.run(main())
