# searchVectorDB

Call **apira-rag MCP** `searchVectorDB`. Do **not** import Apira `python_tools`,
`mcp_tools`, `agents.research_sub_agent`, or other skill markdown. Do **not**
embed locally, walk `${STOCK_RESEARCH_DIR}`, or query Postgres yourself.

## Contract

- **Args:** `query` (ticker or keyword).
- **MCP URL:** `${RAG_MCP_URL}` (Streamable HTTP, typically ends in `/mcp`).
- Open an MCP session to that URL, then `tools/call` with
  `name=searchVectorDB` and `arguments={"query": "<query>"}`.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- The official `mcp` Python client (`streamablehttp_client` + `ClientSession`)
  is fine; raw JSON-RPC is also fine. Do not use LangChain MCP adapters or
  this repo's tool loaders.
- **Stdout:** print only the tool result text (JSON from the server), not
  initialize chatter. If the transport uses SSE, unwrap `data:` JSON.
- Cite only files/chunks returned by MCP. Do not invent filenames or quotes.
