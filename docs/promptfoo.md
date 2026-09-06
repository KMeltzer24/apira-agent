# Promptfoo in Apira — demo notes

What Promptfoo is doing in this project, how to run it, and how to explain it in a demo.

**Config:** [`promptfooconfig.yaml`](../promptfooconfig.yaml) in [apira-agent](https://github.com/KMeltzer24/apira-agent).

---

## Why Promptfoo is here

Goal: put Promptfoo **next to the LangGraph agent**, run evals against the real multi-agent entry point (`POST /chat`), show a small pass/fail suite.

That does **not** mean three separate Promptfoo “agents” (one per graph node).

---

## Why these three tests

The three cases map to the three paths the multi-agent system has:

| # | Test | Graph path exercised | Why it matters |
|---|------|----------------------|----------------|
| 1 | Supervisor chat | Supervisor finishes **without** tools | Chat agent can answer on its own |
| 2 | Alice portfolio | Supervisor → **portfolio** (`login`, `get_portfolio`) | Tools + seed data (AAPL/MSFT, not bob’s NVDA) |
| 3 | Local-folder recommender | Supervisor → portfolio → **research** (`searchLocalFolder`) | Full multi-agent path with Hold/Add/Trim |

So Promptfoo is not “three random prompts.” It is one smoke test per major route of the supervisor graph.

---

## What Promptfoo is

[Promptfoo](https://www.promptfoo.dev/) is an **eval / regression** tool for LLM apps.

In Apira it is:

- A YAML config checked into **apira-agent**
- A CLI (`promptfoo eval`) that sends prompts and checks assertions
- Optional UI (`promptfoo view`) for the last run

It is **not**:

- Part of the running product (frontend/agent do not call it)
- A replacement for Gemini, MCP, or LangGraph
- A unit test of `graph.py` system prompts
- A separate eval of supervisor vs portfolio vs research as three providers

---

## How it works here

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

Important details:

1. **Same API as the UI** — Agent Chat and Recommender also `POST /chat`.
2. **One provider** — `http` → localhost:8100. The whole graph runs **inside** that request.
3. **Scores the final reply only** — Promptfoo never sees which node ran; you infer path from the prompt + what the reply contains.
4. **Live stack required** — Postgres, user/portfolio services, MCP, RAG, agent, and a valid `GOOGLE_API_KEY` must be up ([run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)).

---

## The three tests (what each asserts)

### 1. Supervisor chat

**Prompt:** “What can you help me with in Apira?”

**Expect:** Short answer mentioning portfolio / login / research / stocks; no crash strings.

**Shows:** Supervisor can finish without calling MCP.

### 2. Portfolio path

**Prompt:** Log in as `alice` / `password`, summarize holdings.

**Expect:** Reply contains `AAPL` and `MSFT`; does **not** contain `NVDA` (bob’s ticker).

**Shows:** Portfolio specialist + real DB seed, not a hallucinated portfolio.

### 3. Recommender path (local folder)

**Prompt:** Login, fetch portfolio, use `searchLocalFolder` only, Hold/Add/Trim with reasons.

**Expect:** Mentions hold/add/trim; does not claim `searchVectorDB` / “vector db”.

**Shows:** Research specialist + local research files. No pgvector ingest required for this test.

---

## How to run (demo)

```bash
# Local stack + agent healthy first
curl -s http://localhost:8100/health
# {"status":"ok"}

cd ~/development/apira-agent
REQUEST_TIMEOUT_MS=180000 promptfoo eval
# or: REQUEST_TIMEOUT_MS=180000 npx promptfoo@latest eval

promptfoo view   # browser report of the last run
```

`REQUEST_TIMEOUT_MS=180000` matters: recommender calls Gemini + several tools and can take over a minute.

Expect **3/3** green when the stack is healthy.

---

## What to say in the demo (30 seconds)

1. Promptfoo lives in **apira-agent** next to `graph.py` / `promptfooconfig.yaml`.
2. It hits the **same** `/chat` endpoint as the frontend.
3. Three tests = **chat**, **portfolio tools**, **research/recommender** — the three routes of the supervisor.
4. Run `promptfoo eval` → show 3/3 (or `promptfoo view`).
5. Clarify: we evaluate the **whole multi-agent system as one box**, not each LangGraph node as its own Promptfoo agent.

---

## Limitations (be honest if asked)

| Limitation | Detail |
|------------|--------|
| No per-node scoring | Does not assert “supervisor routed to portfolio.” Only checks the final text. |
| Flaky LLM output | Gemini wording varies; asserts are loose (icontains / keyword JS), not exact strings. |
| Needs live services | Offline / mocked Gemini is not set up; failures can mean stack down, not bad prompts. |
| Slow | Full recommender path can take 1–3 minutes; concurrency is 1. |
| Local folder only | Vector DB / pgvector path is not in the Promptfoo suite. |
| Not CI by default | You run it by hand for demos; no GitHub Action required for this project. |
| Does not grade system prompts | Specialist prompts in `graph.py` are not inspected — only end-to-end replies. |

---

## Files

| File | Role |
|------|------|
| [`promptfooconfig.yaml`](../promptfooconfig.yaml) | Provider URL, three tests, asserts |
| [`README.md`](../README.md) | Short run commands |
| This doc | Demo explanation |

---

## Related

- Multi-agent design: [how-the-agent-works.md](how-the-agent-works.md)
- Local stack: [apira run-locally.md](https://github.com/KMeltzer24/apira/blob/main/docs/run-locally.md)
