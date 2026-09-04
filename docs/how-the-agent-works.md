# How the Apira Agent Works

A LangGraph **supervisor** that routes to **portfolio** and **research** specialists. Specialists call Apira MCP tools; the LLM is Google Gemini. Agent Chat is the supervisor, not a third specialist.

---

## What we built

| Piece | Choice |
|-------|--------|
| Orchestration | **LangGraph** `StateGraph` (`START` → `supervisor` → `portfolio` / `research` → `supervisor` → `END`) |
| Specialists | LangChain `create_agent` subgraphs with partitioned MCP tools |
| Tool loading | **langchain-mcp-adapters** |
| Model | **Gemini** (`gemini-3.1-flash-lite`, via API key) |
| Tool sources | **apira-mcp** (`login`, `get_portfolio`) + **apira-rag** (`searchLocalFolder`, `searchVectorDB`) |

The agent is a client of both MCP servers, in its own repo separate from [apira](https://github.com/KMeltzer24/apira), [apira-mcp](https://github.com/KMeltzer24/apira-mcp), and [apira-rag](https://github.com/KMeltzer24/apira-rag).

---

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph StateGraph + Gemini
  ├── supervisor (no MCP tools) — chat + routing
  ├── portfolio → apira-mcp (:8000/mcp) → backend APIs (:8001 / :8002) → RDS
  └── research → apira-rag (:8200/mcp)
      ├── stock-research files on EC2 (searchLocalFolder)
      └── research_chunks in RDS (searchVectorDB / pgvector)
```

1. Connect to both MCP servers and load tools. Partition: `login` / `get_portfolio` onto **portfolio**; `searchLocalFolder` / `searchVectorDB` onto **research**.
2. Compile a parent graph. The supervisor uses structured output (`portfolio` | `research` | `finish`). Specialists keep their own system prompts (login then holdings; one research tool unless asked for both; Hold/Add/Trim with citations).
3. Run the hard-coded prompt in `agent.py` ("log in as alice, then summarize the portfolio"): supervisor → portfolio → supervisor → END.
4. For recommendations: supervisor → portfolio → supervisor → research → supervisor → END.

The agent never hardcodes the API shape — it discovers tools at runtime. Login, user-service, portfolio-service, and RAG stay tools/services, not graph agents.

---

## Setup

```bash
cd ~/development/apira-agent
python3.11 -m venv .venv          # 3.10+ required; system 3.9 won't work
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # set GOOGLE_API_KEY (aistudio.google.com/apikey)
```

Config lives in `.env`: `MCP_URL`, `RAG_MCP_URL` (both must end in `/mcp`), `LLM_MODEL`, and `GOOGLE_API_KEY`.

---

## Logging and request correlation

`server.py` accepts a valid `X-Request-ID` or generates a UUID, includes it in
the response, and keeps it active throughout the agent run. `agent.py`
propagates that ID in LangGraph metadata and to both MCP servers.

Structured JSON events cover HTTP requests, agent build/run lifecycle (`agent_name`:
`supervisor`, `portfolio`, or `research`), and MCP tool calls. Events include safe
metadata such as durations, model/tool names, argument names, and result sizes.
They omit prompts, replies, tool argument values, credentials, and API keys. Follow them on EC2 with:

```bash
cd ~/apira-agent
sudo docker compose logs -f agent
```

Use the same request ID in the MCP, RAG, and backend container logs to trace one
frontend action end to end. See the canonical
[logging contract](https://github.com/KMeltzer24/apira/blob/main/docs/logging.md).

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

The **Agent Chat** page in [apira-frontend](https://github.com/KMeltzer24/apira-frontend) sends whatever you type to the `/chat` API. The **Recommender** page sends a structured prompt with the selected research tool. To exercise Agent Chat directly:

```bash
curl -s -X POST http://<EC2_PUBLIC_IP>:8100/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
```

For the Recommender path, see [apira-rag/docs/how-stock-recommender-works.md](https://github.com/KMeltzer24/apira-rag/blob/main/docs/how-stock-recommender-works.md).

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `httpx.ConnectError: All connection attempts failed` | An MCP URL is unavailable | Check `MCP_URL`, `RAG_MCP_URL`, and both servers |
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

## Promptfoo

[promptfooconfig.yaml](../promptfooconfig.yaml) sends the same prompts as Agent Chat / Recommender to `POST /chat` and asserts on the final `reply`. It does **not** score supervisor, portfolio, and research as three separate Promptfoo agents — one HTTP call runs the whole graph.

```bash
curl -s http://localhost:8100/health
REQUEST_TIMEOUT_MS=180000 npx promptfoo@latest eval
```

| Case | What it exercises |
|------|-------------------|
| Capabilities question | Supervisor can finish without tools |
| Alice portfolio | Supervisor → portfolio specialist |
| Local-folder recommender | Supervisor → portfolio → research (`searchLocalFolder`) |

---

## Notes

- Verified versions: Python 3.11, langgraph 1.2.6, langchain 1.3.10, langchain-mcp-adapters 0.3.0, langchain-google-genai 4.2.5, fastapi 0.138.0.
- Parent graph lives in `graph.py`; MCP client and `POST /chat` stay in `agent.py` / `server.py`.
- `agent.py` uses a default prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each request.
