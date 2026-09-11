# How the Apira Agent Works

A LangGraph **supervisor** that routes to **portfolio** and **research** specialists. Specialists call Apira MCP tools; the LLM is Google Gemini. Agent Chat is the supervisor, not a third specialist.

---

## What we built

| Piece | Choice |
|-------|--------|
| Orchestration | **LangGraph** `StateGraph` (`START` → `supervisor` → `portfolio` / `research` → `supervisor` → `END`) |
| Specialists | LangChain `create_agent` subgraphs in `agents/portfolio_sub_agent` and `agents/research_sub_agent` |
| Tool loading | Shared **langchain-mcp-adapters** client when `TOOL_MODE=mcp`; each sub-agent selects its allowlist. Other modes use `python_tools/` or `skills/` |
| Model | **Gemini** (`gemini-3.1-flash-lite`, via API key) |
| Tool sources | **apira-mcp** (`login`, `get_portfolio`) + **apira-rag** (`searchLocalFolder`, `searchVectorDB`). `searchVectorDB` is MCP-only; other modes use a local `searchLocalFolder`. |

The agent is a client of both MCP servers, in its own repo separate from [apira](https://github.com/KMeltzer24/apira), [apira-mcp](https://github.com/KMeltzer24/apira-mcp), and [apira-rag](https://github.com/KMeltzer24/apira-rag).

---

## Tool modes (`TOOL_MODE`)

Specialists load **one** packaging at a time. Portfolio tool names stay identical across modes. Research: `searchLocalFolder` exists in every mode; `searchVectorDB` only in `mcp`.

| Mode | Portfolio / research packaging |
|------|--------------------------------|
| `mcp` (default) | MCP allowlists under each agent’s `mcp_tools/` |
| `python` | LangChain `@tool` under `python_tools/` (portfolio → REST; `searchLocalFolder` → local files) |
| `skills_prompt` | `skills/<tool>.md` (natural language only) appended to the system prompt; **no tools bound** |
| `skills_shell` | `skills/<tool>_shell.md` with embedded bash fences (`searchLocalFolder` searches local files) |

Skill files are named after the **tool**, not the agent (`login.md` / `login_shell.md`, not `research.md` / `research_shell.md`).

**Full detail:** [tool-use-scenarios.md](tool-use-scenarios.md).

---

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph StateGraph + Gemini
  ├── supervisor (no MCP tools) — chat + routing
  ├── portfolio → apira-mcp (:8000/mcp) → backend APIs (:8001 / :8002) → Postgres
  └── research → apira-rag (:8200/mcp)
      ├── stock-research/ files (searchLocalFolder)
      └── research_chunks in Postgres (searchVectorDB / pgvector)
```

1. Connect to both MCP servers with one shared client when `TOOL_MODE=mcp`. Each sub-agent loads only its tools via `mcp_tools/` (`login` / `get_portfolio` for portfolio; `searchLocalFolder` / `searchVectorDB` for research). For other modes, specialists load `python_tools/` or `skills/` instead (see **Tool modes** above).
2. Compile a parent graph in `agents/graph.py`. The supervisor (`agents/supervisor/`) uses structured output (`portfolio` | `research` | `finish`). Specialists keep their own system prompts (portfolio: holdings only; research: call the chosen search tool and cite real filenames — never invent `Files: N/A`).
3. Run the hard-coded prompt in `agent.py` ("log in as alice, then summarize the portfolio"): supervisor → portfolio → supervisor → END.
4. For recommendations: supervisor → portfolio → supervisor → research → supervisor → END. Chat starts as `{"role": "user", ...}`; if the LLM tries to `finish` after holdings while the user still asked for search/Hold-Add-Trim and no research tool has run, `enforce_research_routing` forces `research` next.

In `TOOL_MODE=mcp`, the agent does not hardcode the API shape — it discovers tools at runtime. Login, user-service, portfolio-service, and RAG stay tools/services, not graph agents.

---

## Setup

```bash
cd ~/development/apira-agent
python3.11 -m venv .venv          # 3.10+ required; system 3.9 won't work
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # set GOOGLE_API_KEY (aistudio.google.com/apikey)
```

Config lives in `.env`: `TOOL_MODE`, `MCP_URL`, `RAG_MCP_URL` (both must end in `/mcp`), `USER_SERVICE_URL`, `PORTFOLIO_SERVICE_URL`, `STOCK_RESEARCH_DIR`, `LLM_MODEL`, and `GOOGLE_API_KEY`. Full stack: [apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md).

---

## Logging and request correlation

`server.py` accepts a valid `X-Request-ID` or generates a UUID, includes it in
the response, and keeps it active throughout the agent run. `agent.py`
propagates that ID in LangGraph metadata and to both MCP servers.

Structured JSON events cover HTTP requests, agent build/run lifecycle (`agent_name`:
`supervisor`, `portfolio`, or `research`), and MCP tool calls. Events include safe
metadata such as durations, model/tool names, argument names, and result sizes.
They omit prompts, replies, tool argument values, credentials, and API keys. Follow them locally with:

```bash
cd ~/apira-agent
docker compose logs -f agent
```

Use the same request ID in the MCP, RAG, and backend container logs to trace one
frontend action end to end. See the canonical
[logging contract](https://github.com/KMeltzer24/apira/blob/main/docs/logging.md).

---

## How to test

There are two entry points: a hardcoded one-shot prompt, and the custom-prompt API.

### Hardcoded prompt (the assignment demo)

`agent.py` runs the hardcoded `DEFAULT_PROMPT` ("log in as alice, then summarize the portfolio"). Run it inside the container so it inherits `MCP_URL` and `GOOGLE_API_KEY`:

```bash
docker compose exec agent python agent.py
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
curl -s -X POST http://localhost:8100/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
```

For the Recommender path, see [apira-rag/docs/how-stock-recommender-works.md](https://github.com/KMeltzer24/apira-rag/blob/main/docs/how-stock-recommender-works.md).

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `httpx.ConnectError: All connection attempts failed` | An MCP URL is unavailable, or (non-MCP) REST URLs point at `localhost` inside Docker | Check `MCP_URL` / `RAG_MCP_URL`, or use `host.docker.internal` for `USER_SERVICE_URL` / `PORTFOLIO_SERVICE_URL` |
| `Stock research folder not found` | Host path leaked into the container as `STOCK_RESEARCH_DIR` | Set `STOCK_RESEARCH_DIR=/data/stock-research` for Docker |
| `skill bash exited 127: curl: command not found` | Old image without curl | Rebuild agent image (`docker compose up -d --build`); Dockerfile installs curl for `skills_shell` |
| Recommender answers Hold with `Files: N/A` / “no research access” | Supervisor finished after portfolio without research | Ensure current agent build (routing enforcement); logs should show `routed to research` then `searchLocalFolder` / `searchVectorDB` |
| `DefaultCredentialsError` / 401 / 403 from Gemini | Missing or invalid `GOOGLE_API_KEY` | Set a valid key from aistudio.google.com/apikey |
| Gemini `503` high demand / quota exhausted | Temporary capacity or project quota | Retry later, switch `LLM_MODEL`, or raise quota / use a new key |
| `zsh: bad pattern: #` | Inline `#` comment after a command | Run the command alone, no trailing comment |
| Timeout reaching the server | Agent/MCP not running | Start local stack; `curl http://localhost:8100/health` |

---

## Chat UI

`agent.py` is a one-shot CLI demo. For an interactive UI, `server.py` wraps the agent in a FastAPI service exposing `POST /chat` (`{ "message": "..." }` → `{ "reply": "..." }`). The agent is built lazily on the first request, so the server boots instantly.

```bash
docker compose up -d --build
```

Runs on port **8100**. The **Agent Chat** and **Recommender** pages in [apira-frontend](https://github.com/KMeltzer24/apira-frontend) call this endpoint. The agent server stays in this repo (backend); the UI stays in the frontend (client) — same split as the rest of the project.

---

## Promptfoo

[promptfooconfig.yaml](../promptfooconfig.yaml) sends the same prompts as Agent Chat / Recommender to `POST /chat` and asserts on the final `reply`. It does **not** score supervisor, portfolio, and research as three separate Promptfoo agents — one HTTP call runs the whole graph.

```bash
curl -s http://localhost:8100/health
REQUEST_TIMEOUT_MS=180000 promptfoo eval
promptfoo view
```

| Case | What it exercises |
|------|-------------------|
| Capabilities question | Supervisor can finish without tools |
| Alice portfolio | Supervisor → portfolio specialist |
| Local-folder recommender | Supervisor → portfolio → research (`searchLocalFolder`) |

---

## Notes

- Verified versions: Python 3.11, langgraph 1.2.6, langchain 1.3.10, langchain-mcp-adapters 0.3.0, langchain-google-genai 4.2.5, fastapi 0.138.0.
- Parent graph wiring lives in `agents/graph.py`; specialists and supervisor are separate packages under `agents/`. MCP client and `POST /chat` stay in `agent.py` / `server.py`.
- `agent.py` uses a default prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each request.
