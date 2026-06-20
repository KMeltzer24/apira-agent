# Apira Agent

A standalone Python agent that uses the [Apira MCP server](https://github.com/KMeltzer24/apira-mcp) tools to log in a user and retrieve their portfolio — driven by a local LLM via [Ollama](https://ollama.com).

Built with **LangGraph** + **langchain-mcp-adapters**. It is not tied to Cursor or any IDE; it is a plain `python agent.py` program.

**Related repos:**

- Backend APIs: [apira](https://github.com/KMeltzer24/apira)
- MCP server: [apira-mcp](https://github.com/KMeltzer24/apira-mcp)
- Frontend: [apira-frontend](https://github.com/KMeltzer24/apira-frontend)

## How it works

```
agent.py (this repo)
  │  hard-coded prompt: "log in as alice, then get the portfolio"
  ▼
LangGraph ReAct agent + local Ollama model
  │  loads tools over MCP, decides which to call
  ▼
apira-mcp (EC2 :8000/mcp)
  │  login → user-service, get_portfolio → portfolio-service
  ▼
Apira backend APIs → RDS
```

The agent loads the `login` and `get_portfolio` tools from the MCP server at runtime. Given the hard-coded prompt, the model figures out it must call `login` first to get a `user_id`, then call `get_portfolio` with that id, and finally summarize the holdings.

## Prerequisites

1. **Ollama** installed and running, with a tool-capable model pulled:

   ```bash
   # install from https://ollama.com, then:
   ollama pull llama3.1
   ```

   The model must support tool/function calling (e.g. `llama3.1`, `qwen2.5`, `mistral-nemo`). Smaller chat-only models will not reliably call tools.

2. **The apira-mcp server reachable** at the URL in your `.env` (the EC2 deployment on port 8000).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # adjust MCP_URL / OLLAMA_MODEL if needed
```

## Run

```bash
python agent.py
```

Expected output (abridged):

```
Loaded 2 MCP tools: login, get_portfolio

User prompt: Log in as user 'alice' ...

Running agent...

=== Agent answer ===
Alice's portfolio contains 5 holdings: AAPL (150 shares), MSFT (80), ...
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_URL` | `http://localhost:8000/mcp` | Apira MCP endpoint |
| `OLLAMA_MODEL` | `llama3.1` | Local model driving the agent |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |

## Notes

- The user prompt is hard-coded in `agent.py` (`USER_PROMPT`). Change it there to experiment.
- The agent never calls the backend APIs directly — it only uses MCP tools, so it stays decoupled from how the APIs are implemented.
- No authentication on the MCP endpoint (learning project).
