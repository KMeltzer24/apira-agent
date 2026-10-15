# searchVectorDB

Call **apira-rag MCP** `searchVectorDB`. Do **not** import Apira `python_tools`,
`mcp_tools`, `agents.research_sub_agent`, or other skill markdown. Do **not**
embed locally, walk `${STOCK_RESEARCH_DIR}`, or query Postgres yourself.

## Contract

- **Args:** `query` (ticker or keyword).
- **MCP URL:** `${MCP_URL}` (Streamable HTTP, typically ends in `/mcp`).
- Open an MCP session to that URL, then `tools/call` with
  `name=searchVectorDB` and `arguments={"query": "<query>"}`.
- Streamable HTTP **requires** `Accept: application/json, text/event-stream`
  and `Content-Type: application/json` on every request. Missing Accept is
  HTTP 406. After `initialize`, send `Mcp-Session-Id` on later calls.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- The official `mcp` Python client (`streamablehttp_client` + `ClientSession`)
  is fine; raw JSON-RPC is also fine. Do not use LangChain MCP adapters or
  this repo's tool loaders.
- **Stdout:** print only the tool result text (JSON from the server), not
  initialize chatter. If the transport uses SSE, unwrap `data:` JSON.
- Cite only files/chunks returned by MCP. Do not invent filenames or quotes.

## Example python

Adapt this. Keep the Accept header.

```python
import json
import os
import urllib.request

url = os.environ["MCP_URL"]
query = os.environ.get("query", "")
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
if os.environ.get("X_REQUEST_ID"):
    headers["X-Request-ID"] = os.environ["X_REQUEST_ID"]


def rpc(payload, extra=None):
    h = dict(headers)
    if extra:
        h.update(extra)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=h, method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        sid = resp.headers.get("Mcp-Session-Id")
        body = resp.read().decode()
        return sid, body


sid, _ = rpc(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "apira-skill", "version": "0.0.1"},
        },
    }
)
session = {"Mcp-Session-Id": sid} if sid else {}
rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
_, body = rpc(
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "searchVectorDB",
            "arguments": {"query": query},
        },
    },
    session,
)
print(body)
```

