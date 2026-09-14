---
name: getPreviousRecommendation
description: Return the last saved recommendation for a logged-in user_id.
---

# getPreviousRecommendation

Fetch the single most recent recommendation stored for this user.

## Contract

- **Args:** `user_id` (numeric, from a prior login).
- **Endpoint:** `GET ${PORTFOLIO_SERVICE_URL}/recommendation?user_id=<user_id>`.
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON (`user_id`, `body`). `body` is null when none is stored.
- Do not invent a recommendation. Do not call research tools.
