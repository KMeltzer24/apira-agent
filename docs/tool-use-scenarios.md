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
| `skills_prompt` | NL skill markdown → Gemini generates python/bash → run stdout |
| `skills_shell` | Same codegen path; `*_shell.md` sample bash is a **hint** only |

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

When `TOOL_MODE` is `skills_prompt` or `skills_shell`, optional `SKILLS_MCP=true` switches research to `*_MCP.md` / `*_shell_MCP.md`. Generated code calls `RAG_MCP_URL` directly (not `mcp_tools/`, `python_tools/`, or the local-folder skill files). Ignored in `mcp` and `python` modes.

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
| `searchLocalFolder` | Local folder walk in [`python_tools/local_folder_search.py`](../agents/research_sub_agent/python_tools/local_folder_search.py) over `STOCK_RESEARCH_DIR` |
| `searchVectorDB` | **Not registered** (use `TOOL_MODE=mcp` or skills + `SKILLS_MCP`) |

### 3. `skills_prompt`

- Flat files: `skills/<tool>.md` (e.g. `login.md`, `searchLocalFolder.md`) describe the contract in natural language (endpoints, args, stdout).
- Specialists bind real tools with the same names. On each tool call the runtime:
  1. Loads the skill markdown
  2. Asks Gemini to emit **one** fenced `python` / `bash` / `sh` program
  3. Runs that program and returns **stdout** as the tool result

Loader: [`agents/skills_runtime.py`](../agents/skills_runtime.py) → `make_codegen_skill_tool` (`kind="prompt"`).

### 4. `skills_shell`

- Flat files: `skills/<tool>_shell.md` with the same contract **plus** optional sample `bash` fences.
- Same codegen path as `skills_prompt`: Gemini still generates the code that runs. Sample bash is **context/hint** (adapt or rewrite), not auto-executed as the whole tool.

Examples of sample hints:

- Portfolio: `curl` sketches (`login_shell.md`, `get_portfolio_shell.md`)
- Research: inline filesystem search sample (`searchLocalFolder_shell.md`) — not `python_tools` / `local_folder_search`

The agent Docker image installs **`curl`** so generated/sample bash can use it.

### Skills → MCP (`SKILLS_MCP=true`)

Same skills codegen path, but research skill files tell Gemini to call RAG MCP over Streamable HTTP:

- `searchLocalFolder_MCP.md` / `searchLocalFolder_shell_MCP.md`
- `searchVectorDB_MCP.md` / `searchVectorDB_shell_MCP.md`

The generated program must talk to `${RAG_MCP_URL}` only. It must not import this repo’s `python_tools`, `mcp_tools`, or the non-MCP skill markdown.

- Prompt `*_MCP.md`: NL contract (JSON-RPC `tools/call` or any MCP client is fine).
- Shell `*_shell_MCP.md`: sample **curl** JSON-RPC (`initialize` → `Mcp-Session-Id` → `tools/call`), same style as portfolio `*_shell.md`.

---

## Research special case: `searchVectorDB`

Vector search (embeddings, pgvector, ranking) lives in **apira-rag**. The python and default skills paths do not reimplement it.

| Mode | `searchLocalFolder` | `searchVectorDB` |
|------|---------------------|------------------|
| `mcp` | RAG MCP (via `mcp_tools/` allowlist) | RAG MCP |
| `python` | Local files | Not available |
| `skills_prompt` / `skills_shell` | Codegen → local search | Not available |
| same + `SKILLS_MCP=true` | Codegen → RAG MCP (`*_MCP.md`) | Codegen → RAG MCP |

If the user asks for vector search while skills MCP is off and `TOOL_MODE` is not `mcp`, the model has no `searchVectorDB` tool.

The apira-rag pipeline itself was **not** changed.

---

## Layout

```
agents/
  tool_mode.py              # TOOL_MODE validation
  skills_runtime.py         # load skills; Gemini codegen + execute fences
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
      local_folder_search.py  # folder walk used by python @tool
    skills/
      searchLocalFolder.md
      searchLocalFolder_shell.md
      searchLocalFolder_MCP.md
      searchLocalFolder_shell_MCP.md
      searchVectorDB_MCP.md
      searchVectorDB_shell_MCP.md
```

Skill files are named after the **tool** (`login` / `login_shell`), not the agent (`research` / `research_shell`).

---

## Config

| Variable | Used by | Purpose |
|----------|---------|---------|
| `TOOL_MODE` | All | `mcp` \| `python` \| `skills_prompt` \| `skills_shell` |
| `SKILLS_MCP` | `skills_prompt`, `skills_shell` | `true` → research `*_MCP.md` calls RAG MCP |
| `MCP_URL` / `RAG_MCP_URL` | `mcp`; skills + `SKILLS_MCP` | MCP servers |
| `USER_SERVICE_URL` / `PORTFOLIO_SERVICE_URL` | `python`, `skills_prompt`, `skills_shell` | Portfolio REST (python tools; also env for skill-generated code) |
| `STOCK_RESEARCH_DIR` | `python`, `skills_prompt`, `skills_shell` | Local research corpus for `searchLocalFolder` |

Docker mounts `../apira-rag/stock-research` → `/data/stock-research` (override host path with `STOCK_RESEARCH_HOST_PATH`). See `.env.example` and `docker-compose.yml`.

---

## Shared helpers

| Module | Role |
|--------|------|
| `agents/tool_mode.py` | Read/validate `TOOL_MODE`; `SKILLS_MCP` in skills modes |
| `agents/skills_runtime.py` | Skill markdown load; codegen fence extract/run; build skill tools |

---

## Tests

- `tests/test_tool_mode.py` — mode parsing; `SKILLS_MCP` only in skills modes
- `tests/test_python_tools.py` — portfolio tools; research python is local-folder only
- `tests/test_skills_runtime.py` — codegen fence extract/run; skill tool names; research `*_MCP.md` contracts (curl samples, `RAG_MCP_URL`)
- `tests/test_local_folder_search.py` — local folder search / CLI
- `tests/test_graph.py` — sequential graph compile (`logged_in` node); first supervisor cannot choose research; non-MCP modes (including `SKILLS_MCP`) skip `client.get_tools()`; recommender routing after login
- `agents/research_sub_agent/test_agent.py` — specialist build for python / mcp / skills / skills+`SKILLS_MCP`

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

# Shell skills (codegen; sample bash is a hint)
TOOL_MODE=skills_shell docker compose up -d --force-recreate

# NL skills (codegen on each tool call — same outcomes as shell/python for local folder)
TOOL_MODE=skills_prompt docker compose up -d --force-recreate

# Vector via skills codegen that calls RAG MCP (no mcp_tools/ python_tools)
TOOL_MODE=skills_prompt SKILLS_MCP=true docker compose up -d --force-recreate
TOOL_MODE=skills_shell SKILLS_MCP=true docker compose up -d --force-recreate
```
