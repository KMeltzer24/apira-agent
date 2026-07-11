# How the Apira Agent Works

A Python program that automatically logs in a user and retrieves their portfolio — by calling the Apira MCP tools, not the backend APIs directly. The LLM behind it is Google Gemini.

---

## What we built

| Piece | Choice |
|-------|--------|
| Orchestration | **LangGraph** (`create_agent`) |
| Tool loading | **langchain-mcp-adapters** |
| Model | **Gemini** (`gemini-2.5-flash-lite`, via API key) |
| Tool source | **apira-mcp** (`login`, `get_portfolio`, `searchLocalFolder`) |

The agent is a **client** of the MCP server, in its own repo separate from the backend ([apira](https://github.com/KMeltzer24/apira)) and MCP server ([apira-mcp](https://github.com/KMeltzer24/apira-mcp)).

---

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph agent + Gemini
  ▼
apira-mcp (:8000/mcp)
  ▼
backend APIs (:8001 / :8002) → RDS
  + stock-research files on EC2 (searchLocalFolder)
```

1. Connect to the MCP server and load the `login`, `get_portfolio`, and `searchLocalFolder` tools.
2. `create_agent` wires the model to those tools with a system prompt: log in first to get a `user_id`, then fetch the portfolio; for recommendations, search research files and cite them.
3. Run the hard-coded prompt in `agent.py` ("log in as alice, then summarize the portfolio").
4. The model calls `login` → gets `user_id`, then `get_portfolio(user_id)`, then summarizes. For stock recommendations (Recommender tab), it also calls `searchLocalFolder` per ticker and cites the research files.

The agent never hardcodes the API shape — it discovers the tools at runtime and the LLM chains them itself.

---

## Setup

```bash
cd ~/development/apira-agent
python3.11 -m venv .venv          # 3.10+ required; system 3.9 won't work
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # set GOOGLE_API_KEY (aistudio.google.com/apikey)
```

Config lives in `.env`: `MCP_URL` (must end in `/mcp`), `LLM_MODEL`, `GOOGLE_API_KEY`. Gemini needs no local model, so the agent can be hosted on EC2 like the backend and MCP server.

---

## How to test

There are two entry points: a hardcoded one-shot prompt, and the custom-prompt API.

### Hardcoded prompt (the assignment demo)

`agent.py` runs the hardcoded `DEFAULT_PROMPT` ("log in as alice, then summarize the portfolio"). Run it inside the deployed container so it inherits the container's `MCP_URL` and `GOOGLE_API_KEY`:

```bash
# on EC2
sudo docker compose exec agent python agent.py
```

Expected (the exact wording varies — it's an LLM):

```
User prompt: Log in as user 'alice' with password 'password', then retrieve that user's portfolio and summarize the holdings.

Running agent...

=== Agent answer ===
Here are your portfolio holdings:
- Apple Inc. (AAPL): 150 shares
- Microsoft Corp. (MSFT): 80 shares
- Alphabet Inc. (GOOGL): 25 shares
- Amazon.com Inc. (AMZN): 40 shares
- Tesla Inc. (TSLA): 60 shares
```

### Custom prompt (Agent Chat and Recommender)

The **Agent Chat** page in [apira-frontend](https://github.com/KMeltzer24/apira-frontend) sends whatever you type to the `/chat` API. The **Recommender** page sends a structured prompt (login → portfolio → `searchLocalFolder` → hold/add/trim advice). To exercise Agent Chat directly:

```bash
curl -s -X POST http://<EC2_PUBLIC_IP>:8100/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
```

For the Recommender path, see [apira-mcp/docs/how-stock-recommender-works.md](https://github.com/KMeltzer24/apira-mcp/blob/main/docs/how-stock-recommender-works.md).

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `httpx.ConnectError: All connection attempts failed` | No `.env`, so it tried `localhost:8000` | Create `.env`; set `MCP_URL` correctly |
| `DefaultCredentialsError` / 401 / 403 from Gemini | Missing or invalid `GOOGLE_API_KEY` | Set a valid key from aistudio.google.com/apikey |
| `zsh: bad pattern: #` | Inline `#` comment after a command | Run the command alone, no trailing comment |
| Timeout reaching the server | EC2 stopped or your IP changed | Start EC2; open inbound TCP 8000 for your IP |

---

## Chat UI

`agent.py` is a one-shot CLI demo. For an interactive UI, `server.py` wraps the agent in a FastAPI service exposing `POST /chat` (`{ "message": "..." }` → `{ "reply": "..." }`). The agent is built lazily on the first request, so the server boots instantly.

Run it with Docker (recommended — auto-restarts via `restart: unless-stopped`):

```bash
docker compose up -d --build
```

This is deployed on EC2 (port 8100); see the EC2 section in the [README](../README.md). The **Agent Chat** and **Recommender** pages in [apira-frontend](https://github.com/KMeltzer24/apira-frontend) call this endpoint. The agent server stays in this repo (backend); the UI stays in the frontend (client) — same split as the rest of the project.

---

## Notes

- Verified versions: Python 3.11, langgraph 1.2.6, langchain 1.3.10, langchain-mcp-adapters 0.3.0, langchain-google-genai 4.2.5, fastapi 0.138.0.
- `agent.py` uses a default prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each request.
