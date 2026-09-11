---
name: login
description: Authenticate via generated code; sample bash is a hint.
---

# login

Implement a real login against the user-service REST API.

## Contract

- **Args:** `username`, `password`.
- **Endpoint:** `POST ${USER_SERVICE_URL}/login` with JSON
  `{"username": "...", "password": "..."}`.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON response (includes `user_id`).

## Sample bash (hint — adapt or rewrite in your generated fence)

```bash
curl_args=(-sS -X POST "${USER_SERVICE_URL}/login" -H "Content-Type: application/json")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" -d "{\"username\": \"${username}\", \"password\": \"${password}\"}"
```
