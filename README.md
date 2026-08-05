# Apira Agent

A Python agent that uses [apira-mcp](https://github.com/KMeltzer24/apira-mcp) for backend tools and [apira-rag](https://github.com/KMeltzer24/apira-rag) for stock-research tools — driven by **Google Gemini**.

Built with **LangChain**, **LangGraph**, and **langchain-mcp-adapters**. It runs on **EC2** in Docker, alongside the backend and MCP server — the frontend's **Agent Chat** and **Recommender** pages call it there.

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

- **LangChain** provides `create_agent`, the Gemini integration (`ChatGoogleGenerativeAI`), and the MCP adapter used to load tools.
- **LangGraph** is the execution engine underneath LangChain's `create_agent`. It runs the agent loop: send context to Gemini, execute requested MCP tools, return tool results to Gemini, and repeat until the model produces a final answer.

We use LangChain's high-level `create_agent` API, so this project does not manually define LangGraph nodes or edges. The workflow is still executed by LangGraph.

In short: **LangChain supplies the agent API and integrations; LangGraph runs the underlying workflow.**

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph agent + Gemini
  │  loads tools over MCP, decides which to call
  ▼
├── apira-mcp (:8000/mcp)
│   ├── login → user-service
│   └── get_portfolio → portfolio-service
└── apira-rag (:8200/mcp)
    ├── searchLocalFolder → stock-research/ on EC2
    └── searchVectorDB → RDS pgvector (research_chunks)
```

The agent loads tools from both MCP servers at runtime. Given the prompt, the model calls `login` first to get a `user_id`, then `get_portfolio` with that id. For recommendations it uses exactly the research tool requested by the frontend.

`server.py` wraps the agent in a FastAPI service (the agent is built lazily on the first request, so the server boots instantly):

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /chat` | `{ "message": "..." }` → `{ "reply": "..." }` |

## Deploy on EC2 (primary)

The agent runs on EC2 next to the backend and both MCP servers, in Docker with `restart: unless-stopped`. From your Mac, in this repo root:

```bash
tar czf /tmp/apira-agent-deploy.tgz \
  agent.py server.py logging_config.py requirements.txt Dockerfile .dockerignore docker-compose.yml .env.example

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
stdout cover HTTP requests, agent build/run lifecycle, and MCP tool calls,
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
