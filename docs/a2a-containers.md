# A2A agent containers

Apira’s conversational agent runs as three Docker processes that locate one another through the Agent-to-Agent (A2A) protocol and a Nacos registry. [docker-compose.yml](../docker-compose.yml) in this repository defines those three agent services (`supervisor`, `portfolio`, `research`) and Nacos. Nacos is a directory, not a fourth agent.

```bash
cd ~/development/apira-agent
docker compose up -d --build
```

Sequential guest / portfolio / logged-in / research behavior: [how-the-agent-works.md](how-the-agent-works.md).

Supervisor, portfolio, and research are **separate agents**: separate processes, separate images, separate MCP tool trees, **no Python imports** between them. They do not share a process or a tool list. Specialists **register** when they start. The supervisor **does not** scan Nacos at boot. On the first graph hop that needs `portfolio` or `research`, it looks that name up in Nacos (Agent Card), then A2A `POST /a2a` to the URL **on that card**. Nacos is not a message bus; specialists never call each other.

---

## Purpose

The design goal is a **catalog of existing agents** plus **runtime location**, rather than a single process that imports specialist packages.

| Requirement | Mechanism |
|-------------|-----------|
| List what agents exist | Nacos A2A registry (Agent Cards by name) |
| Self-register | Portfolio and research publish card metadata and a Docker-network `/a2a` URL when their process starts |
| Discover | First time the graph needs `portfolio` or `research`, the supervisor looks that **name** up in Nacos (not at supervisor boot; not via well-known HTTP) |
| Call | Using the URL on the card, the supervisor sends graph state to `POST /a2a` (a2a-sdk `ClientFactory`, JSON-RPC) |

Clients (frontend, curl, Promptfoo) call only the supervisor: `POST /chat` on host port `8100`. Specialist HTTP is **not published** to the Mac. The graph still uses the known names `portfolio` and `research`; Nacos answers **where** they are. A new specialist needs a new container that registers and a new node in [agents/graph.py](../agents/graph.py).

---

## Agent separation

Each agent is its own process with its own MCP connections. Compose **builds three images** so a container does not contain another agent’s package or tool tree.

| Isolation | How it is enforced |
|-----------|--------------------|
| Tools not visible to other agents | Each process builds an MCP client with only its servers: supervisor and portfolio → `apira`; research → `research`. Allowlists under each package still filter tool names. Supervisor image does not contain `portfolio_sub_agent` / `research_sub_agent`. |
| Agents not visible outside the registry | Compose does not map `8110`/`8120` to localhost. Discovery does not use well-known HTTP fallback or hardcoded specialist URLs. The host catalog is Nacos (`:8848`). After a card is fetched, A2A still uses the Docker-network URL stored on that card. |

Packages live under `agents/portfolio_sub_agent/`, `agents/research_sub_agent/`, and `agents/supervisor/`. Dockerfile targets `supervisor`, `portfolio`, and `research` strip the other packs. Finding agents at runtime is a **registry** problem.

---

## Process topology

Previously a single compose service `agent` on `:8100` ran supervisor, portfolio, and research in one Python process. The parent graph imported each specialist’s `build_agent`.

| Compose service | `AGENT_ROLE` | Host port | Docker port | Nacos | Responsibility |
|-----------------|--------------|-----------|-------------|-------|----------------|
| `supervisor` | `supervisor` | `8100` | `8100` | Does not register (caller) | FastAPI [`server.py`](../server.py); guest supervisor, logged-in supervisor, `save_recommendation` |
| `portfolio` | `portfolio` | none | `8110` | Registers | Login and holdings specialist |
| `research` | `research` | none | `8120` | Registers | Local-folder and vector research specialist |
| `nacos` | — | `8848` (HTTP), `9848` (gRPC) | same | — | Agent Card and endpoint directory |

Nacos’s A2A registry stores **Agent Cards and `/a2a` endpoints**. Portfolio and research run AgentScope `AgentApp` and therefore register. The supervisor runs FastAPI [`server.py`](../server.py) (`POST /chat`). It is the HTTP entry point and A2A **client**, not an A2A server, so it has no card or `/a2a` path to publish.

All three agent services share the YAML anchor `x-agent-env` (MCP URLs, `TOOL_MODE`, Gemini, `NACOS_SERVER_ADDR=nacos:8848`, `A2A_REGISTRY_ENABLED=true`, `A2A_REGISTRY_TYPE=nacos`). Specialists set `A2A_HOST` to their compose service name so the **registered** URL is reachable on the Docker network (`http://portfolio:8110/a2a`, `http://research:8120/a2a`), not from the host.

```
HTTP client
    POST /chat → supervisor :8100 (published)
                      │
                      │  LangGraph: START → supervisor → portfolio → logged_in
                      │             → research → save_recommendation → logged_in → END
                      │
         discover name ──► Nacos :8848 (published)
                      │
                      │  A2A JSON-RPC POST /a2a (Docker network only)
                      ▼
            portfolio :8110              research :8120
            (AgentApp + Nacos register)  (AgentApp + Nacos register)
                      │                            │
                      ▼                            ▼
                 apira-mcp :8000              apira-rag :8200
```

`logged_in` and `save_recommendation` run inside the supervisor process. They are not compose services and do not register with Nacos.

MCP, RAG, Postgres, and the frontend are started from their own repositories, not this compose file.

---

## Layers: A2A, AgentScope, Nacos

| Layer | Role |
|-------|------|
| **A2A** | HTTP contract: Agent Card (identity, skills, URL) and JSON-RPC tasks on `/a2a` |
| **AgentScope Runtime** | Hosts each specialist as `AgentApp` ([`agents/a2a/specialist_app.py`](../agents/a2a/specialist_app.py) plus per-agent `a2a_main.py`) and, when env enables it, registers with Nacos |
| **Nacos 3.1** | Registry. Console: [http://localhost:8848/nacos](http://localhost:8848/nacos) |

---

## Underlying structure

### Images and entrypoint

Three image targets in [`Dockerfile`](../Dockerfile); [`docker-entrypoint.sh`](../docker-entrypoint.sh) branches on `AGENT_ROLE`:

- `supervisor` → `uvicorn server:app` ([`server.py`](../server.py))
- `portfolio` → `python -m agents.portfolio_sub_agent.a2a_main`
- `research` → `python -m agents.research_sub_agent.a2a_main`

Supervisor `depends_on` healthy Nacos, portfolio, and research so specialists can register before the first chat.

### Specialist server

Each `a2a_main` constructs AgentScope `AgentApp` with `AgentCardWithRuntimeConfig`: name, description, Docker-network `url`, and A2A **skills** (portfolio: `login`, `get_portfolio`; research: `searchLocalFolder`, `searchVectorDB`). `A2A_REGISTRY_*` and `NACOS_SERVER_ADDR` cause AgentScope’s `NacosRegistry` to:

1. **Release (publish) the Agent Card** — identity and skills in Nacos.
2. **Register the endpoint** — address, port, path `/a2a`, JSON-RPC transport.

Registration runs at **process startup**, not on the first user message. AgentScope keeps the Nacos client open for **heartbeat**. Shutdown calls `cleanup()` and closes that connection.

AgentScope may still serve `/.well-known/agent-card.json` **inside** the specialist container. That URL is not published to the host and is not used for supervisor discovery.

`@app.query(framework="langgraph")` is the A2A request handler: it decodes the inbound text as graph state, runs that pack’s LangChain specialist, and yields one assistant message containing the encoded result.

### Parent graph (supervisor process)

[`agents/graph.py`](../agents/graph.py) still compiles a `StateGraph`. Portfolio and research nodes are **not** in-process subgraphs. They are [`build_remote_specialist_node`](../agents/a2a/nodes.py) wrappers that call [`call_specialist`](../agents/a2a/client.py). The supervisor MCP client is created with `mcp_servers=["apira"]` only ([`agents/llm_mcp.py`](../agents/llm_mcp.py)).

### Discover

The supervisor does **not** load the catalog when `server.py` starts. [`agents/a2a/discover.py`](../agents/a2a/discover.py) runs when LangGraph first hits a remote node (`call_specialist` → `_agent_card`). Then:

1. Ask Nacos for the Agent Card named `portfolio` or `research` (`NacosAIService.get_agent_card`).
2. Retry until Nacos has it or attempts are exhausted (no well-known HTTP fallback).
3. Keep that card in memory for later hops in the same supervisor process.

Compose `depends_on` healthy specialists so they can **register before that first hop**. Booting the supervisor alone does not discover anyone.

### Call

[`agents/a2a/client.py`](../agents/a2a/client.py) builds an a2a-sdk client from the card, sends a user text message, and reads the completed task text. [`agents/a2a/payload.py`](../agents/a2a/payload.py) prefixes JSON with `APIRA_STATE_V1:` so `messages`, `logged_in`, `user_id`, and `request_id` survive a text-only A2A hop.

### Tests

[`tests/test_a2a.py`](../tests/test_a2a.py) covers payload round-trip, remote nodes with a mocked `call_specialist`, and Nacos-only discovery (no Docker). [`tests/test_llm_mcp.py`](../tests/test_llm_mcp.py) checks each process only lists its MCP servers.

| Path | Role |
|------|------|
| [docker-compose.yml](../docker-compose.yml) | Four services; per-target images; `AGENT_ROLE`; specialists not published |
| [Dockerfile](../Dockerfile) | `supervisor` / `portfolio` / `research` stages; entrypoint |
| [docker-entrypoint.sh](../docker-entrypoint.sh) | Process selection |
| [server.py](../server.py) | Supervisor HTTP API (`POST /chat`) |
| [agent.py](../agent.py) | Supervisor graph build; MCP servers `apira` only |
| [logging_config.py](../logging_config.py) | Structured logs and `X-Request-ID` |
| [agents/llm_mcp.py](../agents/llm_mcp.py) | Gemini + per-process MCP server list |
| [agents/graph.py](../agents/graph.py) | Sequential graph; remote specialist nodes |
| [agents/state.py](../agents/state.py) | Shared graph state |
| [agents/tool_mode.py](../agents/tool_mode.py) | `TOOL_MODE` / `SKILLS_MCP` |
| [agents/a2a/specialist_app.py](../agents/a2a/specialist_app.py) | Shared AgentApp factory, card, query handler |
| [agents/a2a/discover.py](../agents/a2a/discover.py) | Nacos-only card lookup |
| [agents/a2a/client.py](../agents/a2a/client.py) | A2A JSON-RPC client |
| [agents/a2a/nodes.py](../agents/a2a/nodes.py) | LangGraph node → `call_specialist` |
| [agents/a2a/payload.py](../agents/a2a/payload.py) | `APIRA_STATE_V1` envelope |
| [agents/portfolio_sub_agent/a2a_main.py](../agents/portfolio_sub_agent/a2a_main.py) | Portfolio A2A process + Nacos register |
| [agents/portfolio_sub_agent/agent.py](../agents/portfolio_sub_agent/agent.py) | Portfolio specialist graph |
| [agents/portfolio_sub_agent/mcp_tools/](../agents/portfolio_sub_agent/mcp_tools/) | `login`, `get_portfolio` allowlist |
| [agents/research_sub_agent/a2a_main.py](../agents/research_sub_agent/a2a_main.py) | Research A2A process + Nacos register |
| [agents/research_sub_agent/agent.py](../agents/research_sub_agent/agent.py) | Research specialist graph |
| [agents/research_sub_agent/mcp_tools/](../agents/research_sub_agent/mcp_tools/) | `searchLocalFolder`, `searchVectorDB` allowlist |
| [agents/supervisor/agent.py](../agents/supervisor/agent.py) | Guest and logged-in supervisor hops |
| [agents/supervisor/save_recommendation.py](../agents/supervisor/save_recommendation.py) | Save hop (supervisor process, not Nacos) |
| [agents/supervisor/mcp_tools/](../agents/supervisor/mcp_tools/) | `getPreviousRecommendation` allowlist |
| [tests/test_a2a.py](../tests/test_a2a.py) | Payload, remote nodes, Nacos-only discover |
| [tests/test_llm_mcp.py](../tests/test_llm_mcp.py) | MCP server isolation |

---

## Registration lifetime

Portfolio and research register **when that process starts** (`docker compose up`), not on the first chat. Typical logs:

```text
[NacosRegistry] Agent card published: agent=portfolio
[NacosRegistry] Agent endpoint registered: agent=portfolio, address=portfolio:8110, path=/a2a
```

That is two Nacos writes: the **card** (name, skills, advertised URL) and the **endpoint** (host, port, `/a2a`, JSON-RPC). AgentScope then **keeps the Nacos client open** so heartbeats continue. Idle time (no `/chat`) does **not** unregister them. They stay in the live directory for as long as the container is running.

They are **not** permanently “on” after the first register. Live presence is tied to the process:

| Situation | In the live registry? | Supervisor can call? |
|-----------|----------------------|----------------------|
| Specialist never started | No | No |
| Specialist running (even with no traffic) | Yes — card + endpoint, heartbeats | Yes |
| Specialist stopped (`docker compose stop`, crash, kill) | Heartbeats stop. Nacos treats that **endpoint instance** as gone or unhealthy. Apira has no “registered but inactive” shelf | No |
| Specialist started again | Registers again (same two steps) | Yes |

Graceful shutdown runs AgentScope `cleanup()`, which **closes the Nacos connection**. That stops heartbeats; we do not keep an offline roster. A hard kill skips `cleanup()`; Nacos still drops the instance after missed heartbeats.

Nacos can stay up with specialists down. The console may still show leftover **card** metadata; that is not a live agent. Discover needs a current card/endpoint the supervisor can dial. Until the specialist registers again, lookup fails.

The supervisor **never** registers. Catalog surfaces: compose process list, Nacos console (`http://localhost:8848/nacos`), supervisor logs `a2a.discover.*` (source `nacos`). There is no running / not-running split in the product UI.
