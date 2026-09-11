# Tool Use Scenarios

How apira-agent packages the same capabilities four different ways. Switch with `TOOL_MODE` (one mode at a time).

Related: [how-the-agent-works.md](how-the-agent-works.md), [README](../README.md).

---

## Why this exists

We wanted to compare common agent tool patterns side by side:

| Mode | Idea |
|------|------|
| `mcp` | Tools discovered and called over MCP |
| `python` | In-process LangChain `@tool` functions |
| `skills_prompt` | Markdown skills as system-prompt guidance only (no executable tools) |
| `skills_shell` | Markdown skills with embedded `bash` that run when the tool is called |

Tool **names** stay stable where a tool exists (`login`, `get_portfolio`, `searchLocalFolder`). Packaging changes; the LLM still calls familiar names.

---

## How to switch

Set in `.env` or pass into compose, then recreate the agent:

```bash
TOOL_MODE=mcp docker compose up -d --force-recreate
TOOL_MODE=python docker compose up -d --force-recreate
TOOL_MODE=skills_prompt docker compose up -d --force-recreate
TOOL_MODE=skills_shell docker compose up -d --force-recreate
```

**Docker caveat:** Compose prefers a variable already set in your **shell** over `.env`. If you previously exported `TOOL_MODE`, `USER_SERVICE_URL=http://localhost:…`, or a host `STOCK_RESEARCH_DIR`, those values win inside the container and break non-MCP modes. Prefer prefixing the compose command, or `unset` the overrides. Inside Docker, REST/MCP URLs should use `host.docker.internal`, and `STOCK_RESEARCH_DIR` should be `/data/stock-research`.

Validated in [`agents/tool_mode.py`](../agents/tool_mode.py). Specialists read it in `portfolio_sub_agent/agent.py` and `research_sub_agent/agent.py`. The parent graph only fetches MCP tools when mode is `mcp`.

---

## Mode details

### 1. `mcp` (default)

- Shared `MultiServerMCPClient` connects to **apira-mcp** (`:8000/mcp`) and **apira-rag** (`:8200/mcp`).
- Each specialist **allowlists** tools by name under `mcp_tools/` (implementations live in those servers, not in this repo).
- Portfolio: `login`, `get_portfolio`
- Research: `searchLocalFolder`, `searchVectorDB`

### 2. `python`

LangChain `@tool` under each agent’s `python_tools/`:

| Tool | What runs |
|------|-----------|
| `login` / `get_portfolio` | `httpx` to `USER_SERVICE_URL` / `PORTFOLIO_SERVICE_URL` (same REST as behind apira-mcp) |
| `searchLocalFolder` | Local folder walk in [`local_folder_search.py`](../agents/research_sub_agent/local_folder_search.py) over `STOCK_RESEARCH_DIR` |
| `searchVectorDB` | **Not registered** (MCP-only; see below) |

### 3. `skills_prompt`

- Flat files: `skills/<tool>.md` (e.g. `login.md`, `searchLocalFolder.md`).
- Bodies are concatenated into the specialist system prompt under `## Skills`.
- **No tools bound** — instruction-only demo. The model cannot call login, portfolio, or search.

Loader: [`agents/skills_runtime.py`](../agents/skills_runtime.py) → `load_prompt_skills`.

### 4. `skills_shell`

- Flat files: `skills/<tool>_shell.md` with fenced `bash` / `sh` blocks.
- LangChain tools with the **same names** load that file, extract bash, run via subprocess, pass tool args as env vars, return stdout.

Examples:

- Portfolio: `curl` to user/portfolio services (`login_shell.md`, `get_portfolio_shell.md`)
- Research: `python -m agents.research_sub_agent.local_folder_search` (`searchLocalFolder_shell.md`)

The agent Docker image installs **`curl`** (see `Dockerfile`) so portfolio shell skills work. There is **no** `searchVectorDB_shell.md`.

---

## Research special case: `searchVectorDB`

Vector search (embeddings, pgvector, ranking) lives in **apira-rag**. Duplicating that in the agent would put the same logic in two places and fight the point of the packaging split.

**Decision (with mentor):**

- Give `searchLocalFolder` a real non-MCP path (Python + skills).
- Leave `searchVectorDB` on the RAG MCP server only.

| Mode | `searchLocalFolder` | `searchVectorDB` |
|------|---------------------|------------------|
| `mcp` | RAG MCP | RAG MCP |
| `python` | Local files | Not available |
| `skills_shell` | Local files (bash → local CLI) | Not available |
| `skills_prompt` | Prompt text only | Not available |

If the user asks for vector search while `TOOL_MODE` is not `mcp`, the model has no `searchVectorDB` tool. It may use `searchLocalFolder`, answer without tools, or say it cannot run vector search. To use vector search for real, set `TOOL_MODE=mcp` and restart.

The apira-rag pipeline itself was **not** changed.

---

## Layout

```
agents/
  tool_mode.py              # TOOL_MODE validation
  skills_runtime.py         # load prompt skills; run shell skill bash
  portfolio_sub_agent/
    mcp_tools/              # allowlist login, get_portfolio
    python_tools/           # @tool → REST
    skills/
      login.md
      login_shell.md
      get_portfolio.md
      get_portfolio_shell.md
  research_sub_agent/
    mcp_tools/              # allowlist searchLocalFolder, searchVectorDB
    python_tools/           # @tool searchLocalFolder only
    local_folder_search.py  # shared local search + CLI
    skills/
      searchLocalFolder.md
      searchLocalFolder_shell.md
```

Skill files are named after the **tool** (`login` / `login_shell`), not the agent (`research` / `research_shell`).

---

## Config

| Variable | Used by | Purpose |
|----------|---------|---------|
| `TOOL_MODE` | All | `mcp` \| `python` \| `skills_prompt` \| `skills_shell` |
| `MCP_URL` / `RAG_MCP_URL` | `mcp` | MCP servers |
| `USER_SERVICE_URL` / `PORTFOLIO_SERVICE_URL` | `python`, `skills_shell` | Portfolio REST |
| `STOCK_RESEARCH_DIR` | `python`, `skills_shell` | Local research corpus for `searchLocalFolder` |

Docker mounts `../apira-rag/stock-research` → `/data/stock-research` (override host path with `STOCK_RESEARCH_HOST_PATH`). See `.env.example` and `docker-compose.yml`.

---

## Shared helpers

| Module | Role |
|--------|------|
| `agents/tool_mode.py` | Read/validate `TOOL_MODE` |
| `agents/skills_runtime.py` | Prompt skill injection; bash extraction/execution; build shell skill tools |

---

## Tests

- `tests/test_tool_mode.py` — mode parsing
- `tests/test_python_tools.py` — portfolio tools; research python is local-folder only
- `tests/test_skills_runtime.py` — bash extraction; skill loading
- `tests/test_local_folder_search.py` — local folder search / CLI
- `tests/test_graph.py` — graph compile; non-MCP modes skip `client.get_tools()`; recommender routing enforcement (including dict-style user messages)

```bash
python -m unittest discover -s tests
```

---

## Quick verify

```bash
# MCP (default) — Local folder and Vector DB recommenders in the UI
TOOL_MODE=mcp docker compose up -d --build

# Python packaging (portfolio REST + local folder search)
TOOL_MODE=python docker compose up -d --force-recreate

# Shell skills (needs curl in the image)
TOOL_MODE=skills_shell docker compose up -d --force-recreate

# Prompt-only skills (no real tool calls — expect capability-style answers)
TOOL_MODE=skills_prompt docker compose up -d --force-recreate

# Vector recommender still needs MCP mode
TOOL_MODE=mcp docker compose up -d --force-recreate
```
