---
name: login
description: Authenticate a user before fetching a portfolio.
---

# login

When the user needs to authenticate, treat login as the first required step before any portfolio lookup.

Rules:
- Collect a username and password from the user message (or prior context).
- Explain that successful authentication yields a numeric `user_id`.
- Never invent a `user_id`. If login has not happened in this conversation, say authentication is required.
- Do not fetch holdings until a real `user_id` from login is available.
- Do not discuss research files or trade recommendations.
