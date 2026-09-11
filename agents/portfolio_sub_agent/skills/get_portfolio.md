---
name: get_portfolio
description: Retrieve holdings for an authenticated user_id.
---

# get_portfolio

Use this skill only after login has produced a `user_id`.

Rules:
- Require a numeric `user_id` from a prior successful login in the conversation.
- Summarize holdings clearly (ticker, shares, and company name when present).
- If no `user_id` is available, instruct that login must happen first.
- Do not invent holdings or tickers.
- Do not search research files or recommend trades.
