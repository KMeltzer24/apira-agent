# A2A agent containers

This is the write-up of splitting Apira’s agent into **three Docker containers** that find each other with **AgentScope A2A**.

Yes: [docker-compose.yml](../docker-compose.yml) in **this repo** (`apira-agent`) defines all three agent containers. It also starts **Nacos**, which is a registry, not a fourth agent.

```bash
cd ~/development/apira-agent
docker compose up -d --build
```

---

## What changed

**Before:** one compose service named `agent` on port `8100`. Supervisor, portfolio, and research were Python packages in the **same process**. The supervisor imported specialist code and ran it as LangGraph nodes.

**After:** still one git repo and one Docker image. Three processes, each with `AGENT_ROLE`:

| Compose service | `AGENT_ROLE` | Port | Job |
|-----------------|--------------|------|-----|
| `supervisor` | `supervisor` | `8100` | Frontend `POST /chat`. Discovers specialists, then **calls** them. Guest hop, logged-in hop, save last rec. |
| `portfolio` | `portfolio` | `8110` | Sub-agent. **Registers** itself. Login + holdings (MCP tools). |
| `research` | `research` | `8120` | Sub-agent. **Registers** itself. Stock search (RAG MCP tools). |
| `nacos` | — | `8848` | Directory of Agent Cards. Not an agent. |

The website still only uses `http://localhost:8100`. It never talks to `:8110` or `:8120`.

```
Browser / Promptfoo
        │
        ▼
  supervisor :8100          (LangGraph)
        │  1. look up names in Nacos
        │  2. call specialists over A2A
        ▼
  portfolio :8110     research :8120
        │                    │
        ▼                    ▼
   apira-mcp :8000      apira-rag :8200
```

---

## Why A2A and Nacos

**A2A** (agent-to-agent) is HTTP so one agent can call another by **name and URL**, instead of `import`ing Python.

**AgentScope Runtime** serves each specialist (`AgentApp` in `a2a_server.py`). **a2a-sdk 0.3** is the HTTP protocol (pinned because Runtime requires `<1.0`). AgentScope 2.x’s `A2AAgent` helper expects a2a-sdk 1.x (`TransportProtocol` on `a2a.utils.constants`), so the supervisor does **not** use it. It uses `ClientFactory` instead (`agents/a2a/client.py`), with `TransportProtocol` from `a2a.types`.

1. Each sub-agent starts `a2a_server.py` (AgentScope `AgentApp`).
2. It publishes an Agent Card (`/.well-known/agent-card.json`).
3. It **registers** that card + host/port with Nacos.
4. The supervisor **discovers** `portfolio` and `research` from Nacos (if Nacos is slow, it falls back to the well-known URL on the Docker network).
5. It calls them with a2a-sdk `ClientFactory` (JSON-RPC, non-streaming).

LangGraph routing did **not** change:

```
START → supervisor → portfolio → logged_in → research → save_recommendation → logged_in → END
```

Guest still cannot skip to research. `logged_in` and `save_recommendation` stay **inside the supervisor container**. They are hops, not extra Docker services.

---

## What is in `docker-compose.yml`

Four `services:` blocks:

- `nacos` — `nacos/nacos-server:v3.1.0`
- `supervisor` — `build: .`, `AGENT_ROLE: supervisor`, `8100:8100`
- `portfolio` — same image, `AGENT_ROLE: portfolio`, `8110:8110`
- `research` — same image, `AGENT_ROLE: research`, `8120:8120`

`docker-entrypoint.sh` reads `AGENT_ROLE`: supervisor runs `server.py`; portfolio/research run `a2a_server.py`.

MCP, RAG, Postgres, and the frontend are **not** in this file. They still start from their own repos.

---

## How to verify (maps to the A2A requirements)

Nothing on `:8100` / `:8110` / `:8120` until this stack is up. MCP, RAG, Postgres, and a `GOOGLE_API_KEY` in **this repo’s `.env`** are required for a real chat; the container/register checks only need apira-agent compose. Gemini keys live only in **apira-agent** and **apira-rag** (backend/MCP/frontend do not). Compose interpolates `.env` at container create — after changing the key, recreate: `docker compose up -d --force-recreate supervisor portfolio research`.

```bash
cd ~/development/apira-agent
docker compose up -d --build
docker compose ps
```

You should see **four** services: `nacos`, `supervisor`, `portfolio`, `research` — not a single `agent` container.

### 1. Three agents in separate containers

```bash
docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
curl -s http://localhost:8100/health   # supervisor
curl -s http://localhost:8110/health   # portfolio
curl -s http://localhost:8120/health   # research
```

Three different published ports means three processes. Confirm they are not the same container:

```bash
docker compose exec supervisor printenv AGENT_ROLE   # supervisor
docker compose exec portfolio printenv AGENT_ROLE    # portfolio
docker compose exec research printenv AGENT_ROLE     # research
```

### 2. Each sub-agent registers itself (AgentScope A2A)

Agent Cards (A2A well-known path):

```bash
curl -s http://localhost:8110/.well-known/agent-card.json | python3 -m json.tool
curl -s http://localhost:8120/.well-known/agent-card.json | python3 -m json.tool
```

Expect `"name": "portfolio"` and `"name": "research"`, plus a `url` pointing at that service.

Registration logs (Nacos):

```bash
docker compose logs portfolio | grep -E 'A2A|NacosRegistry|register'
docker compose logs research | grep -E 'A2A|NacosRegistry|register'
```

Look for Agent Card published / endpoint registered. Nacos console: [http://localhost:8848/nacos](http://localhost:8848/nacos) (standalone).

### 3. Supervisor discovers, then calls

Unit tests (no Docker; discovery/call is mocked):

```bash
cd ~/development/apira-agent
source .venv/bin/activate
python -m unittest tests.test_a2a tests.test_graph -q
```

Live discover + call (needs Gemini + MCP/RAG for a full answer):

```bash
# Watch all three while you chat
docker compose logs -f supervisor portfolio research
```

In another terminal:

```bash
curl -s -X POST http://localhost:8100/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
```

In **supervisor** logs, look for:

- `a2a.discover.completed` with `agent_name=portfolio` (Nacos or well-known)
- `a2a.call.completed` / `portfolio specialist started` then `completed`

In **portfolio** logs, the same request should show `http.request` / `agent.run` — that proves the supervisor **called** the other container, not in-process Python.

For research as well, use a Recommender-style prompt (local folder) or Promptfoo:

```bash
curl -s http://localhost:8100/health
REQUEST_TIMEOUT_MS=180000 promptfoo eval
```

A passing alice/recommender case means supervisor → portfolio A2A → logged_in → research A2A.

### What would mean it is *not* working

| Symptom | Meaning |
|---------|---------|
| Only one compose service (`agent`) | Old compose; rebuild from current `docker-compose.yml` |
| `:8110` / `:8120` fail health | Specialists never started |
| No Agent Card JSON | A2A server did not come up |
| Supervisor chat works but **no** lines in `portfolio` / `research` logs | Still in-process (wrong image/graph) |
| `Could not discover A2A agent` | Nacos/register failed and well-known fallback failed |
| `cannot import name 'TransportProtocol'` | Old image still using AgentScope `A2AAgent`; rebuild current `agents/a2a/client.py` |
| JSON-RPC `-32603` / `UnboundLocalError: 'message'` | Specialist finished; AgentScope stream adapter needs a non-`None` `AIMessage.id` (`a2a_server.py` yields `id="{role}-result"`) |
| Gemini `403 PERMISSION_DENIED` | Key/project cannot use `LLM_MODEL`. Put a new key in `.env`, then `--force-recreate` the three agent containers |

---

## Code map

| Path | Role |
|------|------|
| [docker-compose.yml](../docker-compose.yml) | The three agent containers + Nacos |
| [docker-entrypoint.sh](../docker-entrypoint.sh) | Picks supervisor vs specialist process |
| [a2a_server.py](../a2a_server.py) | Specialist A2A server + self-register |
| [agents/a2a/](../agents/a2a/) | Discover, call, GraphState payload |
| [agents/graph.py](../agents/graph.py) | Portfolio/research nodes are A2A clients |
| [server.py](../server.py) | Supervisor `POST /chat` |

Product behavior (tools, Gemini, guest-before-research) is unchanged. Only **where** specialists run changed.

Full agent narrative: [how-the-agent-works.md](how-the-agent-works.md).
