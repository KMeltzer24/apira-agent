---
name: get_portfolio
description: Fetch holdings via generated code; sample bash is a hint.
---

# get_portfolio

Fetch holdings from the portfolio-service REST API.

## Contract

- **Args:** `user_id` from a prior login.
- **Endpoint:** `GET ${PORTFOLIO_SERVICE_URL}/portfolio?user_id=<user_id>`.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON response.

## Sample bash (hint — adapt or rewrite in your generated fence)

```bash
curl_args=(-sS -G "${PORTFOLIO_SERVICE_URL}/portfolio")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" --data-urlencode "user_id=${user_id}"
```
