---
name: get_portfolio
description: Fetch holdings via curl against portfolio-service.
---

# get_portfolio

Call this skill with `user_id` from a prior login. It GETs the portfolio-service holdings endpoint and prints the JSON response.

```bash
curl_args=(-sS -G "${PORTFOLIO_SERVICE_URL}/portfolio")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" --data-urlencode "user_id=${user_id}"
```
