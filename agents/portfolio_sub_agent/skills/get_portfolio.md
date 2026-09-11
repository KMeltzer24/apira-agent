---
name: get_portfolio
description: Retrieve holdings for an authenticated user_id.
---

# get_portfolio

Fetch holdings from the portfolio-service REST API.

## Contract

- **Args:** `user_id` (numeric, from a prior login).
- **Endpoint:** `GET ${PORTFOLIO_SERVICE_URL}/portfolio?user_id=<user_id>`.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON response (`holdings` list with ticker / company / shares).
- Do not invent holdings. Do not search research files or recommend trades.
