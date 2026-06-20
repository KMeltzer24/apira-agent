# How the Apira Agent Works

This doc explains what the Apira agent is, how it was built, how it works at runtime, and how to test that it works end to end.

**What it is:** a standalone Python program that uses a local LLM to automatically log in a user and retrieve their portfolio — by calling the Apira MCP tools, not the backend APIs directly.

**What it is not:** it is not a Cursor plugin or an IDE integration. It is a plain `python agent.py` script you run from a terminal.

---

## What we built

| Piece | Choice | Why |
|-------|--------|-----|
| Orchestration | **LangGraph** (`create_agent`) | Standard agent loop: model decides, tools run, model continues |
| Tool loading | **langchain-mcp-adapters** | Pulls MCP tools into LangChain at runtime |
| Model | **Ollama** (local, `qwen2.5`) | Runs on your Mac, no API key, good tool-calling accuracy |
| Tool source | **apira-mcp** on EC2 | Already exposes `login` and `get_portfolio` over MCP |

The agent lives in its own repo ([apira-agent](https://github.com/KMeltzer24/apira-agent)), separate from the backend ([apira](https://github.com/KMeltzer24/apira)) and the MCP server ([apira-mcp](https://github.com/KMeltzer24/apira-mcp)). It is a **client** of the MCP server, the same way the frontend is a client of the APIs.

---

## How it works

```
agent.py
  │  hard-coded prompt: "log in as alice, then get the portfolio"
  ▼
LangGraph agent + local Ollama model (qwen2.5)
  │  loads tools over MCP, decides which to call
  ▼
apira-mcp (EC2 :8000/mcp)
  │  login → user-service, get_portfolio → portfolio-service
  ▼
Apira backend APIs (:8001 / :8002) → RDS PostgreSQL
```

### Step by step

1. **Load tools.** The agent connects to the MCP server at `MCP_URL` and calls `get_tools()`. It receives two tools — `login` and `get_portfolio` — with their descriptions and parameter schemas.
2. **Build the agent.** `create_agent(model, tools, system_prompt=...)` wires the local Ollama model to those tools. The system prompt tells the model it must log in first to get a `user_id`, then fetch the portfolio.
3. **Run the hard-coded prompt.** The user prompt is fixed in `agent.py`:
   > "Log in as user 'alice' with password 'password', then retrieve that user's portfolio and summarize the holdings."
4. **The model plans.** Seeing only tool descriptions (not hardcoded API calls), the model decides to call `login` with `username="alice"` and `password="password"`.
5. **Tool runs.** The MCP server turns that into `POST /login` on user-service and returns `{"user_id": 1, ...}`.
6. **The model continues.** It now calls `get_portfolio` with `user_id=1`. The MCP server calls `GET /portfolio?user_id=1` on portfolio-service.
7. **The model answers.** It formats the holdings into a readable summary and the script prints it.

The key idea: the agent never hardcodes the API shape. It discovers the tools at runtime and the LLM chains them together on its own.

---

## Key files

| File | Purpose |
|------|---------|
| `agent.py` | The whole agent: loads tools, builds the agent, runs the prompt |
| `requirements.txt` | Pinned, verified dependency versions |
| `.env.example` | Template for `MCP_URL`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL` |
| `.env` | Your local config (gitignored, not committed) |

### Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_URL` | `http://localhost:8000/mcp` | Apira MCP endpoint (set to the EC2 IP in `.env`) |
| `OLLAMA_MODEL` | `qwen2.5` | Local model driving the agent |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |

---

## One-time setup

These steps were done when the agent was first set up. You only repeat them on a new machine.

### 1. Python 3.11 virtual environment

LangGraph/LangChain need Python 3.10+. System Python 3.9 will not work.

```bash
cd ~/development/apira-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Local model via Ollama

Install Ollama from https://ollama.com, then pull a tool-capable model:

```bash
ollama pull qwen2.5
```

Note: `qwen2.5` (~4.4 GB) supports tool calling reliably. Avoid `:cloud` models — they require a paid Ollama subscription and will return a 403.

### 3. Environment file

```bash
cp .env.example .env
```

Confirm `MCP_URL` points at your EC2 MCP server, e.g. `http://3.133.124.58:8000/mcp`.

> Tip: zsh does not allow `#` comments on the same line as a command. Run `cp .env.example .env` on its own line — do not paste a trailing `# comment`, or you will see `zsh: bad pattern: #` and the file will not be copied.

---

## How to test it works

Work through these from quickest to most complete.

### Test 1 — MCP server is reachable

From your Mac:

```bash
curl -i http://3.133.124.58:8000/mcp
```

A **406 Not Acceptable** response is expected and good — it means the server is up but curl is not an MCP client. A timeout means the server or security group is the problem (see Troubleshooting).

### Test 2 — Tools load from the MCP server

This checks the library wiring without needing the model:

```bash
cd ~/development/apira-agent
source .venv/bin/activate
python - <<'PY'
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

async def main():
    client = MultiServerMCPClient({
        "apira": {"url": "http://3.133.124.58:8000/mcp", "transport": "streamable_http"}
    })
    tools = await client.get_tools()
    print("tools:", [t.name for t in tools])

asyncio.run(main())
PY
```

Expected:

```
tools: ['login', 'get_portfolio']
```

### Test 3 — Full agent run (the real test)

```bash
cd ~/development/apira-agent
source .venv/bin/activate
python agent.py
```

Expected output:

```
Loaded 2 MCP tools: login, get_portfolio

User prompt: Log in as user 'alice' with password 'password', then retrieve that user's portfolio and summarize the holdings.

Running agent...

=== Agent answer ===
User 'alice' has the following holdings in their portfolio:

- Apple Inc. (AAPL): 150 shares
- Microsoft Corp. (MSFT): 80 shares
- Alphabet Inc. (GOOGL): 25 shares
- Amazon.com Inc. (AMZN): 40 shares
- Tesla Inc. (TSLA): 60 shares
```

If you see that, the agent works: it logged in and retrieved the portfolio automatically, using only MCP tools and a local model.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|--------------|-----|
| `httpx.ConnectError: All connection attempts failed` | No `.env`, so it tried `localhost:8000` | Create `.env` from `.env.example`; confirm `MCP_URL` is the EC2 IP |
| `zsh: bad pattern: #` | Inline `#` comment after a command | Run the command alone, no trailing comment |
| `this model requires a subscription ... 403` | Using a `:cloud` Ollama model | Pull a local model: `ollama pull qwen2.5`, set `OLLAMA_MODEL=qwen2.5` |
| `406` when running the agent (not curl) | Wrong URL/path | Ensure `MCP_URL` ends in `/mcp` |
| Timeout reaching the MCP server | EC2 stopped, or your IP changed | Start EC2; open inbound TCP 8000 for your IP in the security group |
| Model never calls tools / hallucinates | Model does not support tool calling | Use `qwen2.5`, `llama3.1`, or `mistral-nemo` |
| `ModuleNotFoundError` | venv not active or wrong Python | `source .venv/bin/activate`; ensure it was built with `python3.11` |

---

## Verified configuration

The following versions were tested working together against the live EC2 MCP server:

| Component | Version |
|-----------|---------|
| Python | 3.11 |
| langgraph | 1.2.6 |
| langchain | 1.3.10 |
| langchain-mcp-adapters | 0.3.0 |
| langchain-ollama | 1.1.0 |
| Ollama model | qwen2.5 |

---

## Changing the prompt

The user prompt is hard-coded in `agent.py` as `USER_PROMPT`. To experiment, edit that string and re-run `python agent.py`. For example, try Bob:

```python
USER_PROMPT = (
    "Log in as user 'bob' with password 'password', then retrieve that "
    "user's portfolio and summarize the holdings."
)
```

The agent will log in as bob and return bob's holdings instead.
