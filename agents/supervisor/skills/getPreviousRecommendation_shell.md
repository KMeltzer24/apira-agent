# getPreviousRecommendation

Read the last stored recommendation for this user. Do not invent one. Do not
run research, login, or save a new recommendation.

## Contract

- **Args:** `user_id` (numeric).
- **Endpoint:** `GET ${PORTFOLIO_SERVICE_URL}/recommendation?user_id=<user_id>`
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON (`user_id`, `body`). `body` is JSON `null` when
  none is stored.
- On HTTP error, print the error body and exit non-zero.

## Sample bash

```bash
curl_args=(-sS -f -G "${PORTFOLIO_SERVICE_URL}/recommendation")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" --data-urlencode "user_id=${user_id}"
```
