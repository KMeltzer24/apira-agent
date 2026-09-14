---
name: getPreviousRecommendation
description: Fetch last recommendation via generated code; sample bash is a hint.
---

# getPreviousRecommendation

Fetch the single most recent recommendation stored for this user.

## Contract

- **Args:** `user_id` from a prior login.
- **Endpoint:** `GET ${PORTFOLIO_SERVICE_URL}/recommendation?user_id=<user_id>`.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON response.

## Sample bash (hint — adapt or rewrite in your generated fence)

```bash
curl_args=(-sS -G "${PORTFOLIO_SERVICE_URL}/recommendation")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" --data-urlencode "user_id=${user_id}"
```
