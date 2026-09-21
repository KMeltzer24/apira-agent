# get_portfolio

Call the portfolio-service REST API. Do not invent holdings. Do not search
research files or recommend trades.

## Contract

- **Args:** `user_id` (numeric).
- **Endpoint:** `GET ${PORTFOLIO_SERVICE_URL}/portfolio?user_id=<user_id>`
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON (`holdings` list with ticker / company / shares).
- On HTTP error, print the error body and exit non-zero. Do not fake holdings.

## Sample bash

```bash
curl_args=(-sS -f -G "${PORTFOLIO_SERVICE_URL}/portfolio")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" --data-urlencode "user_id=${user_id}"
```
