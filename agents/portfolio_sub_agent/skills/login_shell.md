---
name: login
description: Authenticate via curl against user-service.
---

# login

Call this skill with `username` and `password`. It posts to the user-service login API and prints the JSON response (including `user_id`).

```bash
curl_args=(-sS -X POST "${USER_SERVICE_URL}/login" -H "Content-Type: application/json")
if [ -n "${X_REQUEST_ID:-}" ]; then
  curl_args+=(-H "X-Request-ID: ${X_REQUEST_ID}")
fi
curl "${curl_args[@]}" -d "{\"username\": \"${username}\", \"password\": \"${password}\"}"
```
