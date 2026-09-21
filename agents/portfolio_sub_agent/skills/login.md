# login

Call the user-service REST API. Do not invent a `user_id`. Do not fetch holdings.

## Contract

- **Args:** `username`, `password`.
- **Endpoint:** `POST ${USER_SERVICE_URL}/login`
- **Body:** `{"username": "<username>", "password": "<password>"}`
- Optional header: `X-Request-ID` from env `X_REQUEST_ID` when set.
- **Stdout:** print the raw JSON response (includes numeric `user_id`).
- On HTTP error, print the error body and exit non-zero. Do not fake success.
