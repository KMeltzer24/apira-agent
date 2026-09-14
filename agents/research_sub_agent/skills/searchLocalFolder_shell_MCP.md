---
name: searchLocalFolder
description: Call RAG MCP searchLocalFolder; sample bash is a hint.
---

# searchLocalFolder

Call **apira-rag MCP** `searchLocalFolder` yourself. This skill is the only
instruction — do **not** import Apira `python_tools`, `mcp_tools`,
`agents.research_sub_agent`, or other skill markdown. Do **not** search the
local folder. Sample below is only a hint.

## Contract

- **Args:** `query`.
- **MCP URL:** `${RAG_MCP_URL}` (Streamable HTTP).
- JSON-RPC `initialize`, then `notifications/initialized`, then `tools/call`
  `searchLocalFolder` with `{"query": "<query>"}`.
- Send `Mcp-Session-Id` from the initialize response on later requests.
- **Stdout:** print the MCP tool result text (JSON from the server).
- Do not invent filenames.

## Sample bash (hint — adapt or rewrite in your generated fence)

```bash
set -euo pipefail
URL="${RAG_MCP_URL}"
Q="${query:-}"
HDR=(-sS -X POST "$URL"
  -H "Content-Type: application/json"
  -H "Accept: application/json, text/event-stream")
if [ -n "${X_REQUEST_ID:-}" ]; then
  HDR+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi

init_headers=$(mktemp)
curl "${HDR[@]}" -D "$init_headers" -o /tmp/mcp-init.body \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"apira-skill","version":"0.0.1"}}}'
SID=$(awk -F': ' 'tolower($1)=="mcp-session-id" {gsub("\r","",$2); print $2}' "$init_headers")
rm -f "$init_headers"
SESSION=(-H "Mcp-Session-Id: ${SID}")

curl "${HDR[@]}" "${SESSION[@]}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# Response may be JSON or SSE (`data: {...}`). Print the payload.
curl "${HDR[@]}" "${SESSION[@]}" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"searchLocalFolder\",\"arguments\":{\"query\":\"${Q}\"}}}"
```
