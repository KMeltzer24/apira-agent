# Apira Agent

A Python agent that uses the [Apira MCP server](https://github.com/KMeltzer24/apira-mcp) tools to log in a user, retrieve their portfolio, and (via `searchLocalFolder`) read stock research files for recommendations — driven by **Google Gemini**.

Built with **LangGraph** + **langchain-mcp-adapters**. It runs on **EC2** in Docker, alongside the backend and MCP server — the frontend's **Agent Chat** and **Recommender** pages call it there.

**Full write-up:** [docs/how-the-agent-works.md](docs/how-the-agent-works.md) — what we built, how it works, and how to test it.

**Stock Recommender (Phase I):** [apira-mcp/docs/how-stock-recommender-works.md](https://github.com/KMeltzer24/apira-mcp/blob/main/docs/how-stock-recommender-works.md) — how the agent uses `searchLocalFolder` for recommendations.

**Related repos:**

- Backend APIs: [apira](https://github.com/KMeltzer24/apira)
- MCP server: [apira-mcp](https://github.com/KMeltzer24/apira-mcp)
- Frontend: [apira-frontend](https://github.com/KMeltzer24/apira-frontend)

## How it works

```
agent.py / server.py (prompt)
  ▼
LangGraph agent + Gemini
  │  loads tools over MCP, decides which to call
  ▼
apira-mcp (:8000/mcp)
  │  login → user-service
  │  get_portfolio → portfolio-service
  │  searchLocalFolder → stock-research/ on EC2
  │  searchVectorDB → RDS pgvector (research_chunks)
  ▼
Apira backend APIs → RDS
```

The agent loads the `login`, `get_portfolio`, and `searchLocalFolder` tools from the MCP server at runtime. Given the prompt, the model calls `login` first to get a `user_id`, then `get_portfolio` with that id. For stock recommendations it also calls `searchLocalFolder` to read research files on EC2 and summarizes actionable advice.

`server.py` wraps the agent in a FastAPI service (the agent is built lazily on the first request, so the server boots instantly):

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /chat` | `{ "message": "..." }` → `{ "reply": "..." }` |

## Deploy on EC2 (primary)

The agent runs on EC2 next to the backend and MCP server, in Docker with `restart: unless-stopped`. From your Mac, in this repo root:

```bash
tar czf /tmp/apira-agent-deploy.tgz \
  agent.py server.py requirements.txt Dockerfile .dockerignore docker-compose.yml .env.example

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
GOOGLE_API_KEY=<your-gemini-key>
```

…and recreate the container so it picks up the key: `sudo docker compose up -d --force-recreate`.

After redeploying **apira-mcp** with new tools, restart the agent so it reloads them: `sudo docker compose restart` in `~/apira-agent/`.

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
| `LLM_MODEL` | `gemini-3.1-flash-lite` | Gemini model |
| `GOOGLE_API_KEY` | — | Gemini API key (required) |
| `CORS_ORIGINS` | `*` | Browser origins allowed to call the API |

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
