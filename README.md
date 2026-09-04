# Apira Agent

A Python agent that uses [apira-mcp](https://github.com/KMeltzer24/apira-mcp) for backend tools and [apira-rag](https://github.com/KMeltzer24/apira-rag) for stock-research tools — driven by **Google Gemini**.

Built with **LangChain**, **LangGraph**, and **langchain-mcp-adapters**. Run it in Docker on your **Mac** ([apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)) or on **EC2**. Agent Chat and Recommender call `POST /chat` on port 8100.

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
    ├── searchLocalFolder → stock-research/ on EC2
    └── searchVectorDB → RDS pgvector (research_chunks)
```

The graph loads tools from both MCP servers at runtime and partitions them onto specialists. The supervisor sends holdings requests to **portfolio** and recommendation/search requests to **research** (portfolio first when holdings are not in the thread yet).

`server.py` wraps the compiled graph in a FastAPI service (built lazily on the first request, so the server boots instantly):

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /chat` | `{ "message": "..." }` → `{ "reply": "..." }` |

## Promptfoo

Eval the **full** LangGraph run (final `reply` only — not each specialist separately) via [promptfooconfig.yaml](promptfooconfig.yaml).

Prerequisites: local stack + agent healthy ([apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)).

```bash
curl -s http://localhost:8100/health
# {"status":"ok"}

cd ~/development/apira-agent
REQUEST_TIMEOUT_MS=180000 npx promptfoo@latest eval
```

Three cases: supervisor chat, alice portfolio (expects AAPL/MSFT), recommender with `searchLocalFolder` only.

## Deploy on EC2 (optional)

The agent runs on EC2 next to the backend and both MCP servers, in Docker with `restart: unless-stopped`. From your Mac, in this repo root:

```bash
tar czf /tmp/apira-agent-deploy.tgz \
  agent.py graph.py server.py logging_config.py requirements.txt Dockerfile .dockerignore docker-compose.yml .env.example

scp -i ../apira/my-ec2-key.pem /tmp/apira-agent-deploy.tgz ec2-user@<EC2_PUBLIC_IP>:/tmp/

ssh -i ../apira/my-ec2-key.pem ec2-user@<EC2_PUBLIC_IP> \
  "mkdir -p ~/apira-agent && \
   tar xzf /tmp/apira-agent-deploy.tgz -C ~/apira-agent && \
   cd ~/apira-agent && \
   test -f .env || cp .env.example .env && \
   sudo docker compose up -d --build"
```

Then on EC2, edit `~/apira-agent/.env`:

```bash
MCP_URL=http://host.docker.internal:8000/mcp   # reaches the apira-mcp container
RAG_MCP_URL=http://host.docker.internal:8200/mcp # reaches apira-rag
GOOGLE_API_KEY=<your-gemini-key>
```

…and recreate the container so it picks up the key: `sudo docker compose up -d --force-recreate`.

After redeploying either MCP server, restart the agent so it reloads tools: `sudo docker compose restart` in `~/apira-agent/`.

Open inbound **TCP 8100** in the EC2 security group for your laptop IP (same as 8000/8001/8002). The tarball never overwrites an existing `~/apira-agent/.env`.

Verify from your Mac:

```bash
curl -X POST http://<EC2_PUBLIC_IP>:8100/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
# -> {"reply":"Here are your portfolio holdings: ..."}
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_URL` | `http://host.docker.internal:8000/mcp` | Apira MCP endpoint (in-container default; on a Mac use `http://<EC2_PUBLIC_IP>:8000/mcp`) |
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
sudo docker compose logs -f agent
sudo docker compose logs --since=10m agent | grep '<request-id>'
```

## Local development (optional)

To run the agent on your Mac instead of EC2 (e.g. while iterating on the code):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set GOOGLE_API_KEY, and MCP_URL=http://<EC2_PUBLIC_IP>:8000/mcp
```

One-shot CLI demo:

```bash
python agent.py
```

Or run the API locally in Docker (reaches the EC2 MCP server via the public IP in `.env`):

```bash
docker compose up -d --build
curl -X POST http://localhost:8100/chat -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
```

## Notes

- `agent.py` runs a one-shot prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each chat request.
- The agent never calls the backend APIs directly — it only uses MCP tools, so it stays decoupled from how the APIs are implemented.
- No authentication on the MCP endpoint or the agent API (learning project). Keep `GOOGLE_API_KEY` in `.env` (gitignored), never in git.
