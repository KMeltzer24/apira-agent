# How the Apira Agent Works

A LangGraph **supervisor** that routes **sequentially** through **portfolio**, then a **logged_in** hop, then **research** when needed. Portfolio and research each run in their own Docker container, register with Nacos over AgentScope A2A, and are discovered by the supervisor. Specialists call Apira MCP tools; the LLM is Google Gemini. Agent Chat is the supervisor, not a third specialist.

---

## What we built

| Piece | Choice |
|-------|--------|
| Orchestration | **LangGraph** `StateGraph` (`START` → `supervisor` → `portfolio` → `logged_in` → `research` → `save_recommendation` → `logged_in` → `END`). Portfolio/research hops are A2A calls, not in-process subgraphs. |
| Specialists | LangChain `create_agent` in `agents/portfolio_sub_agent` and `agents/research_sub_agent`, each served by AgentScope `AgentApp` in its own container |
| Discovery | Sub-agents register Agent Cards with **Nacos 3.1**; supervisor uses `NacosAgentCardResolver` then a2a-sdk `ClientFactory` (not AgentScope `A2AAgent`) |
| Tool loading | Shared **langchain-mcp-adapters** client when `TOOL_MODE=mcp`; each sub-agent selects its allowlist. Other modes use `python_tools/` or `skills/` |
| Model | **Gemini** (`gemini-3.1-flash-lite`, via API key) |
| Tool sources | **apira-mcp** (`login`, `get_portfolio`, `getPreviousRecommendation`, `saveRecommendation`) + **apira-rag** (`searchLocalFolder`, `searchVectorDB`). Last recommendation lives in Apira Postgres (`recommendations`). `searchVectorDB` is on RAG MCP (`TOOL_MODE=mcp` or skills + `SKILLS_MCP=true`); other modes use a local `searchLocalFolder`. |

**A2A three-container split:** [a2a-containers.md](a2a-containers.md) (`docker-compose.yml` in this repo).

---

## Tool modes (`TOOL_MODE`)

Specialists load **one** packaging at a time. Portfolio tool names stay identical across modes. Research: `searchLocalFolder` exists in every mode; `searchVectorDB` in `mcp`, and in skills modes when `SKILLS_MCP=true`.

| Mode | Portfolio / research packaging |
|------|--------------------------------|
| `mcp` (default) | MCP allowlists under each agent’s `mcp_tools/` |
| `python` | LangChain `@tool` under `python_tools/` (portfolio → REST; `searchLocalFolder` → local files) |
| `skills_prompt` | `skills/<tool>.md` → Gemini generates python/bash → run. With `SKILLS_MCP=true`, research uses `*_MCP.md` (RAG MCP, including `searchVectorDB`) |
| `skills_shell` | `skills/<tool>_shell.md` same codegen path; sample bash is a hint. With `SKILLS_MCP=true`, research uses `*_shell_MCP.md` (`curl` JSON-RPC to RAG MCP) |

Skill files are named after the **tool**, not the agent (`login.md` / `login_shell.md`, not `research.md` / `research_shell.md`).

**Full detail:** [tool-use-scenarios.md](tool-use-scenarios.md).

---

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph StateGraph + Gemini (sequential specialists; POST /chat is HTTP only)
  ├── supervisor — chat, or route to portfolio only (no tools)
  ├── portfolio (A2A, Docker network only) → apira-mcp (:8000/mcp) → backend APIs
  ├── logged_in — post-portfolio: `getPreviousRecommendation` tool, or route to research
  ├── save_recommendation — supervisor upsert after research (not an LLM tool)
  └── research (A2A, Docker network only) → apira-rag (:8200/mcp)
```

On startup, **portfolio** and **research** register themselves with Nacos (`:8848`). The supervisor does not look them up at boot. When a chat routes to a specialist, it loads that Agent Card **from Nacos only** and calls `/a2a` on the Docker network. Guest routing is unchanged: research is unreachable until portfolio has run.

## Three separate agents

`docker compose up` starts **three agent processes** plus Nacos. Compose builds a **separate image per agent** so another agent’s tools are not on that disk.

| Compose service | Host port | What it is |
|-----------------|-----------|------------|
| `supervisor` | `8100` | Frontend `POST /chat`. Guest hop, logged-in hop, `save_recommendation`. Discovers and **calls** the other two. |
| `portfolio` | none | Sub-agent. **Registers** itself, then runs login/holdings. |
| `research` | none | Sub-agent. **Registers** itself, then runs search tools. |
| `nacos` | `8848` | A2A registry (not an agent). |

Three Docker images; `AGENT_ROLE` picks which process starts. The UI never talks to specialist HTTP; those ports are not published.

### How a request runs

1. Each specialist container connects to MCP when `TOOL_MODE=mcp` and loads only its allowlist (`login` / `get_portfolio` for portfolio; `searchLocalFolder` / `searchVectorDB` for research). The supervisor container loads `getPreviousRecommendation` for the logged-in hop. For other modes, specialists load `python_tools/` or `skills/` instead (see **Tool modes** above).
2. Compile a parent graph in `agents/graph.py`. Portfolio and research nodes are A2A clients. The first supervisor’s structured output is `portfolio` | `finish` (no tools). After portfolio, the logged-in supervisor binds `getPreviousRecommendation` and may choose `research` | `finish` | `portfolio`. Last rec is that tool, not a graph destination. See [get-previous-recommendation.md](get-previous-recommendation.md).
3. Run the hard-coded prompt in `agent.py` ("log in as alice, then summarize the portfolio"): supervisor → portfolio → logged_in → END.
4. For recommendations: supervisor → portfolio → logged_in → research → save_recommendation → logged_in → END. The save hop upserts `recommendations`; research only searches. Asking for the last rec later: logged_in calls `getPreviousRecommendation`. The first hop cannot skip to research; `enforce_guest_routing` sends research/last-rec asks to portfolio first. After holdings, if the user still asked for search/Hold-Add-Trim and no research tool has run, `enforce_research_routing` forces `research` next. `POST /chat` always enters this graph; it does not call MCP tools itself.

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

Config lives in `.env`: `TOOL_MODE`, `SKILLS_MCP`, `MCP_URL`, `RAG_MCP_URL` (both must end in `/mcp`), `USER_SERVICE_URL`, `PORTFOLIO_SERVICE_URL`, `STOCK_RESEARCH_DIR`, `LLM_MODEL`, and `GOOGLE_API_KEY`. Full stack: [apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md).

---

## Logging and request correlation

`server.py` accepts a valid `X-Request-ID` or generates a UUID, includes it in
the response, and keeps it active throughout the agent run. `agent.py`
propagates that ID in LangGraph metadata and to both MCP servers.

Structured JSON events cover HTTP requests, agent build/run lifecycle (`agent_name`:
`supervisor`, `logged_in`, `portfolio`, `research`, or `save_recommendation`), and MCP tool calls. Events include safe
metadata such as durations, model/tool names, argument names, and result sizes.
They omit prompts, replies, tool argument values, credentials, and API keys. Follow them locally with:

```bash
cd ~/apira-agent
docker compose logs -f supervisor
```

Use the same request ID in the MCP, RAG, and backend container logs to trace one
frontend action end to end. See the canonical
[logging contract](https://github.com/KMeltzer24/apira/blob/main/docs/logging.md).

---

## How to test

### Specialists on their own (no supervisor)

Portfolio and research each have a `test_agent.py` next to the agent code. These call `build_agent` directly — they do not compile the parent graph. Gemini and MCP are stubbed (fake chat model + fake tool client) so the tests stay local and fast. They still switch `TOOL_MODE` (`python`, `mcp`, `skills_prompt`, `skills_shell`) to check that each specialist loads tools and returns messages.

```bash
python -m unittest agents.portfolio_sub_agent.test_agent
python -m unittest agents.research_sub_agent.test_agent
python -m unittest discover -s tests
```

Supervisor parse/routing and graph compile live in `tests/test_graph.py`. These unit tests do **not** replace Promptfoo: they do not score real replies or hit live login/search.

There are two live entry points: a hardcoded one-shot prompt, and the custom-prompt API.

### Hardcoded prompt

`agent.py` runs the hardcoded `DEFAULT_PROMPT` ("log in as alice, then summarize the portfolio"). Run it inside the supervisor container so it inherits `MCP_URL` and `GOOGLE_API_KEY`:

```bash
docker compose exec supervisor python agent.py
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
| Recommender answers Hold with `Files: N/A` / “no research access” | Logged-in supervisor finished after portfolio without research | Ensure current agent build (guest cannot skip portfolio; `enforce_research_routing` after login); logs should show `logged_in` then `routed to research` then `searchLocalFolder` / `searchVectorDB` |
| `DefaultCredentialsError` / 401 / 403 from Gemini | Missing, stale container env, or project denied for `LLM_MODEL` | Put a valid key in **apira-agent `.env`** (RAG has its own for embeddings). Recreate containers: `docker compose up -d --force-recreate supervisor portfolio research` |
| JSON-RPC `-32603` Internal error | Supervisor reached portfolio; specialist reply failed A2A encoding | See [a2a-containers.md](a2a-containers.md); rebuild specialist images |
| Gemini `503` high demand / quota exhausted | Temporary capacity or project quota | Retry later, switch `LLM_MODEL`, or raise quota / use a new key |
| `zsh: bad pattern: #` | Inline `#` comment after a command | Run the command alone, no trailing comment |
| Timeout reaching the server | Agent/MCP not running | Start local stack; `curl http://localhost:8100/health` |

---

## Chat UI

`agent.py` is a one-shot CLI demo. For an interactive UI, `server.py` wraps the agent in a FastAPI service exposing `POST /chat` (`{ "message": "..." }` → `{ "reply": "..." }`). The agent is built lazily on the first request, so the server boots instantly.

```bash
docker compose up -d --build
```

That starts Nacos plus **supervisor** (host `:8100`), **portfolio**, and **research** (specialists on the Docker network only). The **Agent Chat** and **Recommender** pages still call only `POST /chat` on `:8100`. The UI stays in the frontend; the three agent processes stay in this repo.

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
| Alice portfolio | Supervisor → portfolio → logged_in |
| Local-folder recommender | Supervisor → portfolio → logged_in → research (`searchLocalFolder`) → save_recommendation |

---

## Notes

- Verified versions: Python 3.11, langgraph 1.2.6, langchain 1.3.10, langchain-mcp-adapters 0.3.0, langchain-google-genai 4.2.5, fastapi 0.138.0, agentscope 2.0.8, agentscope-runtime 1.1.6.post2, a2a-sdk 0.3.26.
- Parent graph wiring lives in `agents/graph.py`; specialists and supervisor are separate packages under `agents/`. Root `agent.py` builds the Gemini/MCP client (apira-mcp only) and imports that graph; `server.py` exposes `POST /chat` on the **supervisor** container. Portfolio and research are separate A2A processes (`a2a_main.py`) that register with Nacos.
- `agent.py` uses a default prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each request.
