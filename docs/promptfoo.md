# Promptfoo in Apira — demo notes

Overview of Promptfoo in this project: purpose, how it runs, the four tests, and limits.

**Config:** [`promptfooconfig.yaml`](../promptfooconfig.yaml) in [apira-agent](https://github.com/KMeltzer24/apira-agent).

---

## Purpose

Promptfoo lives in **apira-agent** next to the LangGraph code. It evaluates the live multi-agent entry point (`POST /chat`) with a small pass/fail suite.

It does not treat supervisor, portfolio, and research as three separate Promptfoo providers. One HTTP call runs the full graph; assertions run on the final `reply`.

---

## Why these four tests

The suite maps to the main paths of the multi-agent system:

| # | Test | Graph path exercised | Why it matters |
|---|------|----------------------|----------------|
| 1 | Supervisor chat | Supervisor finishes **without** tools | Chat can complete with no MCP calls |
| 2 | Alice portfolio | Supervisor → **portfolio** (`login`, `get_portfolio`) | Tools + seed data (share counts; not bob’s tickers) |
| 3 | Local-folder recommender | Supervisor → portfolio → **research** (`searchLocalFolder`) | Disk research files + Hold/Add/Trim |
| 4 | Vector-DB recommender | Supervisor → portfolio → **research** (`searchVectorDB`) | pgvector ingest + semantic search |

Each test covers one major supervisor route rather than an arbitrary prompt.

**Prerequisite for test 4:** local Postgres has been ingested (`research_chunks` populated). See [apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md) and `apira-rag` ingest scripts. The agent must run with `TOOL_MODE=mcp` (default) because `searchVectorDB` is MCP-only — see [tool-use-scenarios.md](tool-use-scenarios.md).

---

## What Promptfoo is

[Promptfoo](https://www.promptfoo.dev/) is an eval / regression tool for LLM apps.

In Apira it provides:

- A YAML config in **apira-agent**
- A CLI (`promptfoo eval`) that sends prompts and checks assertions
- An optional UI (`promptfoo view`) for the last run

It is not:

- Part of the running product (the frontend and agent do not call it)
- A replacement for Gemini, MCP, or LangGraph
- A unit test of specialist system prompts
- A separate eval of each LangGraph node

---

## How it works

```text
promptfooconfig.yaml
  │  for each test: prompt + asserts
  ▼
HTTP POST http://localhost:8100/chat
  body: { "message": "<test prompt>" }
  ▼
apira-agent (LangGraph)
  supervisor → portfolio and/or research → final reply
  ▼
Promptfoo reads json.reply
  ▼
Assertions (contains AAPL, Hold/Add/Trim, no Traceback, …)
  → pass / fail
```

1. **Same API as the UI** — Agent Chat and Recommender also `POST /chat`.
2. **One provider** — `http` → `localhost:8100`. The full graph runs inside that request.
3. **Final reply only** — Promptfoo does not observe which node ran; path coverage comes from the prompt design and reply content.
4. **Live stack required** — Postgres, user/portfolio services, MCP, RAG, agent, and a valid `GOOGLE_API_KEY` must be up ([run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)).

---

## The four tests

### 1. Supervisor chat

**Prompt:** “What can you help me with in Apira?”

**Expect:** No crash/`503`; reply long enough to be real; mentions both account/portfolio help **and** research/recommendations.

**Covers:** Supervisor finish without MCP.

### 2. Portfolio path

**Prompt:** Log in as `alice` / `password`, summarize holdings with share counts.

**Expect:** All alice tickers (`AAPL`, `MSFT`, `GOOGL`, `AMZN`, `TSLA`); correct seed share counts; no bob tickers (`NVDA`, `META`).

**Covers:** Portfolio specialist against the seeded database.

### 3. Recommender path (local folder)

**Prompt:** Login, fetch portfolio, use `searchLocalFolder` only, Hold/Add/Trim with reasons.

**Expect:** No crash/`503`/vector-db wording; at least three Hold/Add/Trim actions; several alice tickers; at least one research filename citation (`.md` / `.txt` or known note name).

**Covers:** Research specialist and local research files (no pgvector required).

### 4. Recommender path (vector DB)

**Prompt:** Login, fetch portfolio, use `searchVectorDB` only, Hold/Add/Trim with reasons.

**Expect:** No crash/`503`/local-folder wording; at least three Hold/Add/Trim actions; several alice tickers; at least one corpus citation (analyst note or extracted earnings file).

**Covers:** Research specialist + `research_chunks` semantic search (requires prior ingest).

---

## How to run

```bash
# Local stack + agent healthy first
curl -s http://localhost:8100/health
# {"status":"ok"}

cd ~/development/apira-agent
REQUEST_TIMEOUT_MS=180000 promptfoo eval
# or: REQUEST_TIMEOUT_MS=180000 npx promptfoo@latest eval

promptfoo view   # browser report of the last run
```

Use `REQUEST_TIMEOUT_MS=180000` because recommender paths can exceed one minute. A healthy stack with ingest should report **4/4** pass.

---

## Demo talking points

1. Promptfoo lives in **apira-agent** next to `agents/` / `promptfooconfig.yaml`.
2. Evals hit the same `/chat` endpoint as the frontend.
3. Four tests cover chat, portfolio tools, local-folder research, and vector-DB research.
4. `promptfoo eval` (or `promptfoo view`) shows pass/fail for the suite.
5. Scoring is end-to-end on the final reply, not per LangGraph node.

---

## Limitations

| Limitation | Detail |
|------------|--------|
| No per-node scoring | Does not assert routing decisions; only checks final text |
| Variable LLM output | Asserts use loose matching (`icontains` / keyword checks), not exact strings |
| Needs live services | No offline Gemini mock; stack outages look like eval failures |
| Slow | Recommender path can take 1–3 minutes; concurrency is 1 |
| Vector DB needs ingest | Test 4 fails if `research_chunks` is empty |
| Manual runs | No CI workflow required for this project |
| System prompts not graded | Agent package prompts are not inspected; only end-to-end replies |

---

## Files

| File | Role |
|------|------|
| [`promptfooconfig.yaml`](../promptfooconfig.yaml) | Provider URL, four tests, asserts |
| [`README.md`](../README.md) | Short run commands |
| This doc | Demo explanation |

---

## Related

- Multi-agent design: [how-the-agent-works.md](how-the-agent-works.md)
- Local stack: [apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)
