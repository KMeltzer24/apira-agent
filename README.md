# Apira Agent

A Python agent that uses [apira-mcp](https://github.com/KMeltzer24/apira-mcp) for backend tools and [apira-rag](https://github.com/KMeltzer24/apira-rag) for stock-research tools — driven by **Google Gemini**.

Built with **LangChain**, **LangGraph**, and **langchain-mcp-adapters**. Run it in Docker on your **Mac** ([apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)). Agent Chat and Recommender call `POST /chat` on port 8100.

**Full write-up:** [docs/how-the-agent-works.md](docs/how-the-agent-works.md) — what we built, how it works, and how to test it.

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
START → supervisor → portfolio | research → supervisor → END
```

| Node | Role | MCP tools |
|------|------|-----------|
| **supervisor** | Chat agent: answer directly or route | none |
| **portfolio** | Login and holdings | `login`, `get_portfolio` |
| **research** | Citations and Hold/Add/Trim | `searchLocalFolder`, `searchVectorDB` |

Agent Chat and Stock Recommender both `POST /chat`; the supervisor decides which specialist(s) to run. Login and the FastAPI services stay tools, not agents.

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph StateGraph + Gemini
  │  supervisor routes; specialists call MCP
  ▼
├── portfolio → apira-mcp (:8000/mcp)
│   ├── login → user-service
│   └── get_portfolio → portfolio-service
└── research → apira-rag (:8200/mcp)
    ├── searchLocalFolder → stock-research/
    └── searchVectorDB → Postgres pgvector (research_chunks)
```

The graph loads tools from both MCP servers at runtime and partitions them onto specialists. The supervisor sends holdings requests to **portfolio** and recommendation/search requests to **research** (portfolio first when holdings are not in the thread yet).

`server.py` wraps the compiled graph in a FastAPI service (built lazily on the first request, so the server boots instantly):

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /chat` | `{ "message": "..." }` → `{ "reply": "..." }` |

## Promptfoo

Eval the **full** LangGraph run (final `reply` only — not each specialist separately) via [promptfooconfig.yaml](promptfooconfig.yaml).

**Demo write-up:** [docs/promptfoo.md](docs/promptfoo.md) — what it does, the three tests, how to run, limitations.

Prerequisites: local stack + agent healthy ([apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)).

```bash
curl -s http://localhost:8100/health
# {"status":"ok"}

cd ~/development/apira-agent
REQUEST_TIMEOUT_MS=180000 promptfoo eval
# or: REQUEST_TIMEOUT_MS=180000 npx promptfoo@latest eval
promptfoo view   # optional HTML report of the last run
```

Three cases: supervisor chat, alice portfolio (expects AAPL/MSFT), recommender with `searchLocalFolder` only.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_URL` | `http://host.docker.internal:8000/mcp` | Apira MCP endpoint |
| `RAG_MCP_URL` | `http://host.docker.internal:8200/mcp` | Apira RAG MCP endpoint |
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
- The agent never calls the backend APIs directly — it only uses MCP tools, so it stays decoupled from how the APIs are implemented.
- No authentication on the MCP endpoint or the agent API (learning project). Keep `GOOGLE_API_KEY` in `.env` (gitignored), never in git.
