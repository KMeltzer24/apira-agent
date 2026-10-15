# searchLocalFolder

Call **apira-rag MCP** `searchLocalFolder`. Do **not** import Apira
`python_tools`, `mcp_tools`, `agents.research_sub_agent`, or other skill
markdown. Do **not** search the local folder.

## Contract

- **Args:** `query`.
- **MCP URL:** `${MCP_URL}` (Streamable HTTP).
- JSON-RPC `initialize`, then `notifications/initialized`, then `tools/call`
  `searchLocalFolder` with `{"query": "<query>"}`.
- Send `Mcp-Session-Id` from the initialize response on later requests.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the MCP tool result text (JSON from the server). If the
  response is SSE, unwrap `data:` lines. Do not invent filenames.

## Sample bash

```bash
set -euo pipefail
URL="${MCP_URL}"
Q="${query:-}"
HDR=(-sS -X POST "$URL"
  -H "Content-Type: application/json"
  -H "Accept: application/json, text/event-stream")
if [ -n "${X_REQUEST_ID:-}" ]; then
  HDR+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi

init_headers=$(mktemp)
curl "${HDR[@]}" -D "$init_headers" -o /dev/null \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"apira-skill","version":"0.0.1"}}}'
SID=$(awk -F': ' 'tolower($1)=="mcp-session-id" {gsub("\r","",$2); print $2}' "$init_headers")
rm -f "$init_headers"
SESSION=(-H "Mcp-Session-Id: ${SID}")

curl "${HDR[@]}" "${SESSION[@]}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

curl "${HDR[@]}" "${SESSION[@]}" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"searchLocalFolder\",\"arguments\":{\"query\":\"${Q}\"}}}"
```
