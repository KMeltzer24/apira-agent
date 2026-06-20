# Apira Agent

A standalone Python agent that uses the [Apira MCP server](https://github.com/KMeltzer24/apira-mcp) tools to log in a user and retrieve their portfolio — driven by a local LLM via [Ollama](https://ollama.com).

Built with **LangGraph** + **langchain-mcp-adapters**.

**Full write-up:** [docs/how-the-agent-works.md](docs/how-the-agent-works.md) — what we built, how it works, and how to test it.

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

1. **Python 3.11+** (LangGraph/LangChain require 3.10+; this was verified on 3.11).

2. **Ollama** installed and running, with a tool-capable **local** model pulled:

   ```bash
   # install from https://ollama.com, then:
   ollama pull qwen2.5
   ```

   The model must support tool/function calling. `qwen2.5` (~4.4 GB) gives the best tool-calling reliability per GB; `llama3.1` and `mistral-nemo` also work. Small chat-only models (and cloud `:cloud` models that require a subscription) will not work.

3. **The apira-mcp server reachable** at the URL in your `.env` (the EC2 deployment on port 8000).

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # adjust MCP_URL / OLLAMA_MODEL if needed
```

## Run (one-shot CLI demo)

```bash
python agent.py
```

Expected output (abridged):

```
User prompt: Log in as user 'alice' ...

Running agent...

=== Agent answer ===
Alice's portfolio contains 5 holdings: AAPL (150 shares), MSFT (80), ...
```

## Run as an API (for the chat UI)

`server.py` wraps the agent in a small FastAPI service so a frontend can chat with it:

```bash
uvicorn server:app --host 127.0.0.1 --port 8100
```

Then:

```bash
curl -X POST http://127.0.0.1:8100/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
# -> {"reply":"Here is your current portfolio: ..."}
```

The chat UI lives in [apira-frontend](https://github.com/KMeltzer24/apira-frontend) (the "Agent Chat" page) and calls this `/chat` endpoint. The agent runs locally because Ollama is local, so the server binds to your Mac.

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /chat` | `{ "message": "..." }` → `{ "reply": "..." }` |

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_URL` | `http://localhost:8000/mcp` | Apira MCP endpoint |
| `OLLAMA_MODEL` | `qwen2.5` | Local model driving the agent |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `CORS_ORIGINS` | `*` | Comma-separated browser origins allowed to call the API |

## Notes

- `agent.py` runs a one-shot prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each chat request.
- The agent never calls the backend APIs directly — it only uses MCP tools, so it stays decoupled from how the APIs are implemented.
- No authentication on the MCP endpoint or the agent API (learning project).
