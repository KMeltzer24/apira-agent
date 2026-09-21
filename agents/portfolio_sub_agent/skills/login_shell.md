# login

Call the user-service REST API. Do not invent a `user_id`. Do not fetch holdings.

## Contract

- **Args:** `username`, `password`.
- **Endpoint:** `POST ${USER_SERVICE_URL}/login`
- **Body:** `{"username": "<username>", "password": "<password>"}`
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON response (includes numeric `user_id`).
- On HTTP error, print the error body and exit non-zero. Do not fake success.

## Sample bash

```bash
curl_args=(-sS -f -X POST "${USER_SERVICE_URL}/login" -H "Content-Type: application/json")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" -d "{\"username\": \"${username}\", \"password\": \"${password}\"}"
```
