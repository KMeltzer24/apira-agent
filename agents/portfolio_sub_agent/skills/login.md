---
name: login
description: Authenticate a user before fetching a portfolio.
---

# login

Implement a real login against the user-service REST API.

## Contract

- **Args:** `username`, `password` (from the tool call / env).
- **Endpoint:** `POST ${USER_SERVICE_URL}/login` with JSON body
  `{"username": "...", "password": "..."}`.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON response (must include numeric `user_id`).
- Never invent a `user_id`. Do not fetch holdings here.
