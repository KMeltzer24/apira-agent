# Apira Agent

A Python agent that uses [apira-mcp](https://github.com/KMeltzer24/apira-mcp) for backend tools and [apira-rag](https://github.com/KMeltzer24/apira-rag) for stock-research tools — driven by **Google Gemini**.

Built with **LangChain**, **LangGraph**, and **langchain-mcp-adapters**. Run it in Docker on your **Mac** ([apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)). Agent Chat and Recommender call `POST /chat` on port 8100.

**Full write-up:** [docs/how-the-agent-works.md](docs/how-the-agent-works.md) — what we built, how it works, and how to test it.

**Tool use scenarios:** [docs/tool-use-scenarios.md](docs/tool-use-scenarios.md) — `TOOL_MODE` (MCP, Python `@tool`, skills prompt, skills shell).

**Stock Recommender:** [apira-rag/docs/how-stock-recommender-works.md](https://github.com/KMeltzer24/apira-rag/blob/main/docs/how-stock-recommender-works.md).

**Logging contract:** [apira/docs/logging.md](https://github.com/KMeltzer24/apira/blob/main/docs/logging.md).
**How logging works:** [apira/docs/how-logging-works.md](https://github.com/KMeltzer24/apira/blob/main/docs/how-logging-works.md).

**Related repos:**

- Backend APIs: [apira](https://github.com/KMeltzer24/apira)
- Backend MCP: [apira-mcp](https://github.com/KMeltzer24/apira-mcp)
- Research MCP: [apira-rag](https://github.com/KMeltzer24/apira-rag)
- Frontend: [apira-frontend](https://github.com/KMeltzer24/apira-frontend)

## LangChain vs LangGraph

Apira uses **both**:

- **LangChain** provides `create_agent` (specialist subgraphs), Gemini (`ChatGoogleGenerativeAI`), and the MCP adapter.
- **LangGraph** owns the parent graph: named nodes and edges, not a hidden `create_agent` loop.

```
START → supervisor → portfolio → logged_in → research → logged_in → END
```

The first supervisor cannot route to research. Portfolio sets `logged_in` on graph state; only that hop may send work to research. `POST /chat` is the HTTP door (not a graph node). The supervisor answers chat or routes.

| Node | Role | MCP tools |
|------|------|-----------|
| **supervisor** | Pre-login: answer chat or send to portfolio | none (`agents/supervisor/`) |
| **portfolio** | Login and holdings; marks the session logged in | `login`, `get_portfolio` (`agents/portfolio_sub_agent/mcp_tools/`) |
| **logged_in** | Post-portfolio supervisor: research or finish | none (`agents/supervisor/`) |
| **research** | Citations and Hold/Add/Trim | `searchLocalFolder`, `searchVectorDB` (`agents/research_sub_agent/mcp_tools/`) |

Tool **names stay the same** across packaging modes. Set `TOOL_MODE` to switch how specialists load them:

| `TOOL_MODE` | What specialists use |
|-------------|----------------------|
| `mcp` (default) | Remote MCP tools via allowlists under `mcp_tools/` |
| `python` | In-process LangChain `@tool`s under `python_tools/` (portfolio → REST; `searchLocalFolder` → local files) |
| `skills_prompt` | NL `skills/<tool>.md` → Gemini generates python/bash → execute (real tools). With `SKILLS_MCP=true`, research uses `*_MCP.md` and calls RAG MCP directly (includes `searchVectorDB`) |
| `skills_shell` | `skills/<tool>_shell.md` same codegen path; sample bash is a hint. With `SKILLS_MCP=true`, research uses `*_shell_MCP.md` (folder + vector via MCP) |

Agent Chat and Stock Recommender both `POST /chat`. The first supervisor can only send work to portfolio; research runs only after the logged-in hop. Login and the FastAPI services stay tools, not agents.

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph StateGraph + Gemini
  │  sequential: supervisor → portfolio → logged_in → research
  ▼
├── portfolio → apira-mcp (:8000/mcp)
│   ├── login → user-service
│   └── get_portfolio → portfolio-service
└── research → apira-rag (:8200/mcp)  (only after logged_in)
    ├── searchLocalFolder → stock-research/
    └── searchVectorDB → Postgres pgvector (research_chunks)
```

The graph loads tools from a shared MCP client; each sub-agent keeps its own allowlist under `mcp_tools/` (`portfolio_sub_agent`, `research_sub_agent`). The first supervisor answers or sends to portfolio; research is unlocked only after that specialist returns. Specialists do not share tools with each other in the codebase.

`server.py` wraps the compiled graph in a FastAPI service (built lazily on the first request, so the server boots instantly):

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /chat` | `{ "message": "..." }` → `{ "reply": "..." }` |

## Unit tests

Specialists can be tested **without** the supervisor, Gemini, or live MCP. Each package has `test_agent.py` that calls `build_agent` directly and stubs the LLM plus MCP client. `TOOL_MODE` is switched through `python`, `mcp`, and both skill modes (including `SKILLS_MCP` for research `*_MCP.md`).

```bash
python -m unittest agents.portfolio_sub_agent.test_agent
python -m unittest agents.research_sub_agent.test_agent
python -m unittest discover -s tests   # graph wiring, routing, tools
```

Supervisor routing stays in `tests/test_graph.py`. Live Gemini + MCP still go through Promptfoo / `POST /chat`.

## Promptfoo

Eval the **full** LangGraph run (final `reply` only — not each specialist separately) via [promptfooconfig.yaml](promptfooconfig.yaml).

**Demo write-up:** [docs/promptfoo.md](docs/promptfoo.md) — what it does, the four tests, how to run, limitations.

Prerequisites: local stack + agent healthy ([apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)).

```bash
curl -s http://localhost:8100/health
# {"status":"ok"}

cd ~/development/apira-agent
REQUEST_TIMEOUT_MS=180000 promptfoo eval
# or: REQUEST_TIMEOUT_MS=180000 npx promptfoo@latest eval
promptfoo view   # optional HTML report of the last run
```

Four cases: supervisor chat, alice portfolio (share counts), local-folder recommender, vector-DB recommender (needs ingest).

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `TOOL_MODE` | `mcp` | Tool packaging: `mcp`, `python`, `skills_prompt`, or `skills_shell` |
| `SKILLS_MCP` | `false` | When `TOOL_MODE` is `skills_prompt` or `skills_shell`, research skills call RAG MCP from `*_MCP.md` files |
| `MCP_URL` | `http://host.docker.internal:8000/mcp` | Apira MCP endpoint |
| `RAG_MCP_URL` | `http://host.docker.internal:8200/mcp` | Apira RAG MCP endpoint |
| `USER_SERVICE_URL` | `http://host.docker.internal:8001` | user-service REST (python / skills_shell) |
| `PORTFOLIO_SERVICE_URL` | `http://host.docker.internal:8002` | portfolio-service REST (python / skills_shell) |
| `STOCK_RESEARCH_DIR` | `/data/stock-research` | Local research corpus (python / skills_shell `searchLocalFolder`) |
| `LLM_MODEL` | `gemini-3.1-flash-lite` | Gemini model |
| `GOOGLE_API_KEY` | — | Gemini API key (required) |
| `CORS_ORIGINS` | `*` | Browser origins allowed to call the API |
| `LOG_LEVEL` | `INFO` | Minimum structured-log level |
| `LOG_FORMAT` | `json` | `json` for container logs or `text` for local debugging |
| `ENVIRONMENT` | `development` | Environment label included in each log event |
| `SERVICE_NAME` | `apira-agent` | Service label included in each log event |

## Logging and correlation

The API accepts or generates an `X-Request-ID`, returns it to the caller, and
propagates it through LangGraph and calls to both MCP servers. JSON events on
stdout cover HTTP requests, supervisor/specialist runs (`agent_name`), and MCP tool calls,
including safe metadata such as durations and argument names. Prompts, replies,
tool argument values, passwords, and keys are not logged.

```bash
docker compose logs -f agent
docker compose logs --since=10m agent | grep '<request-id>'
```

## Local development

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set GOOGLE_API_KEY, MCP_URL, RAG_MCP_URL (see run-locally.md)
```

One-shot CLI demo:

```bash
python agent.py
```

Or run the API in Docker:

```bash
docker compose up -d --build
curl -X POST http://localhost:8100/chat -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
```

## Notes

- `agent.py` runs a one-shot prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each chat request.
- The agent never calls the backend APIs directly **in `TOOL_MODE=mcp`** — it uses MCP tools. With `TOOL_MODE=python`, portfolio `@tool`s call user/portfolio REST and `searchLocalFolder` uses `python_tools/local_folder_search.py`. With `skills_prompt` / `skills_shell`, the same tool names run via Gemini codegen from skill markdown. `searchVectorDB` is available in `TOOL_MODE=mcp`, and in skills modes when `SKILLS_MCP=true` (generated code calls RAG MCP; it does not use `mcp_tools/` or `python_tools`).
- No authentication on the MCP endpoint or the agent API (learning project). Keep `GOOGLE_API_KEY` in `.env` (gitignored), never in git.
