# searchLocalFolder

Call **apira-rag MCP** `searchLocalFolder`. Do **not** import Apira
`python_tools`, `mcp_tools`, `agents.research_sub_agent`, or other skill
markdown. Do **not** walk `${STOCK_RESEARCH_DIR}` on disk.

## Contract

- **Args:** `query` (ticker or keyword).
- **MCP URL:** `${MCP_URL}` (Streamable HTTP, typically ends in `/mcp`).
- Open an MCP session to that URL, then `tools/call` with
  `name=searchLocalFolder` and `arguments={"query": "<query>"}`.
- Streamable HTTP **requires** `Accept: application/json, text/event-stream`
  and `Content-Type: application/json` on every request. Missing Accept is
  HTTP 406. After `initialize`, send `Mcp-Session-Id` on later calls.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- The official `mcp` Python client (`streamablehttp_client` + `ClientSession`)
  is fine; raw JSON-RPC is also fine. Do not use LangChain MCP adapters or
  this repo's tool loaders.
- **Stdout:** print only the tool result text (JSON from the server), not
  initialize chatter. If the transport uses SSE, unwrap `data:` JSON.
- Cite only files returned by MCP. Do not invent filenames or file text.
