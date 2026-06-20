# How the Apira Agent Works

A standalone Python program that uses a local LLM to automatically log in a user and retrieve their portfolio — by calling the Apira MCP tools, not the backend APIs directly. It runs as a plain `python agent.py` program.

---

## What we built

| Piece | Choice |
|-------|--------|
| Orchestration | **LangGraph** (`create_agent`) |
| Tool loading | **langchain-mcp-adapters** |
| Model | **Ollama** (local, `qwen2.5`) |
| Tool source | **apira-mcp** on EC2 (`login`, `get_portfolio`) |

The agent is a **client** of the MCP server, in its own repo separate from the backend ([apira](https://github.com/KMeltzer24/apira)) and MCP server ([apira-mcp](https://github.com/KMeltzer24/apira-mcp)).

---

## How it works

```
agent.py (hard-coded prompt)
  ▼
LangGraph agent + local Ollama model (qwen2.5)
  ▼
apira-mcp (EC2 :8000/mcp)
  ▼
backend APIs (:8001 / :8002) → RDS
```

1. Connect to the MCP server and load the `login` and `get_portfolio` tools.
2. `create_agent` wires the model to those tools with a system prompt: log in first to get a `user_id`, then fetch the portfolio.
3. Run the hard-coded prompt in `agent.py` ("log in as alice, then summarize the portfolio").
4. The model calls `login` → gets `user_id`, then `get_portfolio(user_id)`, then summarizes.

The agent never hardcodes the API shape — it discovers the tools at runtime and the LLM chains them itself.

---

## Setup

```bash
cd ~/development/apira-agent
python3.11 -m venv .venv          # 3.10+ required; system 3.9 won't work
source .venv/bin/activate
pip install -r requirements.txt

ollama pull qwen2.5               # tool-capable local model (~4.4 GB)
cp .env.example .env              # confirm MCP_URL points at the EC2 IP
```

Config lives in `.env`: `MCP_URL` (must end in `/mcp`), `OLLAMA_MODEL`, `OLLAMA_BASE_URL`.

---

## How to test

```bash
source .venv/bin/activate
python agent.py
```

Expected:

```
Loaded 2 MCP tools: login, get_portfolio
...
=== Agent answer ===
User 'alice' has the following holdings in their portfolio:
- Apple Inc. (AAPL): 150 shares
- Microsoft Corp. (MSFT): 80 shares
- Alphabet Inc. (GOOGL): 25 shares
- Amazon.com Inc. (AMZN): 40 shares
- Tesla Inc. (TSLA): 60 shares
```

That confirms the agent logged in and retrieved the portfolio automatically using only MCP tools and a local model.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `httpx.ConnectError: All connection attempts failed` | No `.env`, so it tried `localhost:8000` | Create `.env`; set `MCP_URL` to the EC2 IP |
| `zsh: bad pattern: #` | Inline `#` comment after a command | Run the command alone, no trailing comment |
| `this model requires a subscription ... 403` | A `:cloud` Ollama model | `ollama pull qwen2.5`, set `OLLAMA_MODEL=qwen2.5` |
| Timeout reaching the server | EC2 stopped or your IP changed | Start EC2; open inbound TCP 8000 for your IP |
| Model never calls tools | Model lacks tool calling | Use `qwen2.5`, `llama3.1`, or `mistral-nemo` |

---

## Chat UI

`agent.py` is a one-shot CLI demo. For an interactive UI, `server.py` wraps the agent in a FastAPI service exposing `POST /chat` (`{ "message": "..." }` → `{ "reply": "..." }`). The agent is built lazily on the first request, so the server boots instantly.

Run it with Docker (recommended — auto-restarts via `restart: unless-stopped`):

```bash
docker compose up -d --build
```

The container reaches Ollama on the Mac host via `host.docker.internal`. Or run it directly: `uvicorn server:app --host 127.0.0.1 --port 8100`.

The chat page in [apira-frontend](https://github.com/KMeltzer24/apira-frontend) calls this endpoint. The agent server stays in this repo (backend); the UI stays in the frontend (client) — same split as the rest of the project.

---

## Notes

- Verified versions: Python 3.11, langgraph 1.2.6, langchain 1.3.10, langchain-mcp-adapters 0.3.0, langchain-ollama 1.1.0, fastapi 0.138.0, model `qwen2.5`.
- `agent.py` uses a default prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each request.
