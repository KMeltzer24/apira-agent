# Apira Agent

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-supervisor-1C3C3C)](https://langchain-ai.github.io/langgraph/)
[![Gemini](https://img.shields.io/badge/Gemini-API-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

**LangGraph multi-agent runtime** for Apira: a supervisor plus A2A specialists (portfolio, research) registered in Nacos. Gemini does the reasoning; **MCP** (FastMCP in [apira-rag](https://github.com/KMeltzer24/apira-rag)) is how tools are called.

`POST /chat` on **:8100**. Specialists are not published to localhost — the supervisor discovers them.

Apira is four repos. **Clone + run order:** [apira README](https://github.com/KMeltzer24/apira). Start backend and rag before this repo.

```
START → supervisor → portfolio → logged_in → research → save_recommendation → logged_in → END
```

| Node | Tools |
|------|--------|
| supervisor (guest) | none |
| portfolio | `login`, `get_portfolio` |
| logged_in | `getPreviousRecommendation` |
| research | `searchLocalFolder`, `searchVectorDB` |
| save_recommendation | REST `PUT /recommendation` (not an LLM tool) |

Specialists are not published to localhost; the supervisor discovers them through Nacos. `TOOL_MODE=mcp` is the default. `python`, `skills_prompt`, and `skills_shell` load the same tool names a different way.

## Talks to

| Sibling | How |
|---------|-----|
| [apira](https://github.com/KMeltzer24/apira) | REST `:8001` / `:8002` (`python` / `skills_shell` modes) |
| [apira-rag](https://github.com/KMeltzer24/apira-rag) | `MCP_URL=http://host.docker.internal:8000/mcp`; corpus at `../apira-rag/stock-research` |
| [apira-frontend](https://github.com/KMeltzer24/apira-frontend) | UI calls `POST /chat` |

Keep this clone next to `apira-rag` so the compose volume for `stock-research` resolves.

## Run

Need [Docker Desktop](https://www.docker.com/products/docker-desktop/) and a [Gemini API key](https://aistudio.google.com/apikey).

```bash
git clone https://github.com/KMeltzer24/apira-agent.git
cd apira-agent
cp .env.example .env
# set GOOGLE_API_KEY
docker compose up -d --build
curl -s http://localhost:8100/health
```

Optional live eval (stack must be up): `REQUEST_TIMEOUT_MS=180000 promptfoo eval`.
