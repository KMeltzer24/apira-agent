# Apira Agent

A Python agent that uses the [Apira MCP server](https://github.com/KMeltzer24/apira-mcp) tools to log in a user and retrieve their portfolio. The LLM behind it is pluggable: **Gemini** via API key (default, runs anywhere) or a **local Ollama** model (free, Mac-only).

Built with **LangGraph** + **langchain-mcp-adapters**. Deployed on **EC2** in Docker, alongside the backend and MCP server.

**Full write-up:** [docs/how-the-agent-works.md](docs/how-the-agent-works.md) — what we built, how it works, and how to test it.

**Related repos:**

- Backend APIs: [apira](https://github.com/KMeltzer24/apira)
- MCP server: [apira-mcp](https://github.com/KMeltzer24/apira-mcp)
- Frontend: [apira-frontend](https://github.com/KMeltzer24/apira-frontend)

## How it works

```
agent.py / server.py
  │  prompt: "log in as alice, then get the portfolio"
  ▼
LangGraph agent + LLM (Gemini API, or local Ollama)
  │  loads tools over MCP, decides which to call
  ▼
apira-mcp (:8000/mcp)
  │  login → user-service, get_portfolio → portfolio-service
  ▼
Apira backend APIs → RDS
```

The agent loads the `login` and `get_portfolio` tools from the MCP server at runtime. Given the prompt, the model calls `login` first to get a `user_id`, then `get_portfolio` with that id, and summarizes the holdings.

## LLM providers

Set `LLM_PROVIDER` in `.env`:

| Provider | `LLM_PROVIDER` | Needs | Runs on |
|----------|----------------|-------|---------|
| **Gemini** (default) | `google_genai` | `GOOGLE_API_KEY` ([get one](https://aistudio.google.com/apikey)) | Anywhere (EC2 or Mac) |
| **Ollama** (local) | `ollama` | Ollama + `ollama pull qwen2.5` | Mac only |

Gemini is the default because it needs no local model, so the agent can be hosted on EC2 like the rest of the stack.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set GOOGLE_API_KEY (Gemini) or switch LLM_PROVIDER=ollama
```

## Run (one-shot CLI demo)

```bash
python agent.py
```

## Run as an API (for the chat UI)

`server.py` wraps the agent in a FastAPI service. The agent is built lazily on the first request, so the server boots instantly.

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /chat` | `{ "message": "..." }` → `{ "reply": "..." }` |

```bash
docker compose up -d --build      # port 8100, restart: unless-stopped
```

Verify:

```bash
curl -X POST http://localhost:8100/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Log in as alice (password: password) and show my portfolio"}'
# -> {"reply":"Here is your current portfolio: ..."}
```

The chat UI lives in [apira-frontend](https://github.com/KMeltzer24/apira-frontend) (the "Agent Chat" page) and calls this `/chat` endpoint.

## Deploy on EC2

The agent is deployed on EC2 next to the backend and MCP server. From your Mac, in this repo root:

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
LLM_PROVIDER=google_genai
GOOGLE_API_KEY=<your-gemini-key>
```

Open inbound **TCP 8100** in the EC2 security group for your laptop IP (same as 8000/8001/8002). The tarball never overwrites an existing `~/apira-agent/.env`.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_URL` | `http://localhost:8000/mcp` | Apira MCP endpoint |
| `LLM_PROVIDER` | `ollama` (code) / `google_genai` (.env) | `google_genai` or `ollama` |
| `LLM_MODEL` | `gemini-2.5-flash` | Gemini model (when using `google_genai`) |
| `GOOGLE_API_KEY` | — | Gemini API key (when using `google_genai`) |
| `OLLAMA_MODEL` | `qwen2.5` | Local model (when using `ollama`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `CORS_ORIGINS` | `*` | Browser origins allowed to call the API |

## Notes

- `agent.py` runs a one-shot prompt (`DEFAULT_PROMPT`); `server.py` takes the prompt from each chat request.
- The agent never calls the backend APIs directly — it only uses MCP tools, so it stays decoupled from how the APIs are implemented.
- No authentication on the MCP endpoint or the agent API (learning project). Keep `GOOGLE_API_KEY` in `.env` (gitignored), never in git.
