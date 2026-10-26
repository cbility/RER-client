# Session Auth API

This API returns authenticated RER cookies for use with the separate client API.

## What It Does

For each request, the session-auth Lambda:

1. checks SmartSuite for cached RER cookies
2. validates those cookies against the RER portal
3. returns cached cookies when they are valid
4. otherwise starts the RER login and MFA flow asynchronously and returns `202 Accepted`
5. stores refreshed cookies back in SmartSuite

The client retrieves cookies here, then sends them to the client API.

## Base URL

Use the CloudFormation stack output named `RERSessionAuthApiUrl`.

Example shape:

```text
https://YOUR_API_ID.execute-api.eu-west-2.amazonaws.com/Prod/
```

Important:
- Call the API root URL.

## Authentication

Send the API Gateway API key in the `x-api-key` header.

Example:

```http
x-api-key: YOUR_SESSION_AUTH_API_KEY
```

This is the separate API key for the session-auth API, not the client API key.

## Examples

### Get cookies

```bash
curl \
  -H "x-api-key: YOUR_SESSION_AUTH_API_KEY" \
  "https://YOUR_API_ID.execute-api.eu-west-2.amazonaws.com/Prod/"
```

You can also pass `recipientReference` as a query parameter, but JSON body input is preferred.

## Response Behavior

- `200 OK`: `{"cookies": {"name": "value"}}`; send these cookies to the client API.
- `202 Accepted`: `{"status": "refreshing"}`; retry after the background refresh completes.

## Operational Notes

- If valid cookies are cached in SmartSuite, requests complete quickly.
- If cookies are missing or expired, the API returns `202` while a background Lambda invocation completes RER login and MFA.
- SmartSuite stores the cookie payload for reuse across requests.

## Required Lambda Configuration

Deploy the stack with `scripts/deploy.sh` from the repository root. It loads the
values below from `.env` and passes them as CloudFormation parameters. Do not
run plain `sam deploy` afterward, because it will not load `.env`.

The deployed session-auth Lambda expects these environment variables to be configured:

- `RER_EMAIL`
- `RER_PASSWORD`
- `SMARTSUITE_API_TOKEN`
- `SMARTSUITE_ACCOUNT_ID`
- `SMARTSUITE_TABLE_ID`
- `SMARTSUITE_RECORD_ID`
- `SMARTSUITE_COOKIES_FIELD`

Optional:

- `SMARTSUITE_REFRESHED_AT_FIELD`
- `SMARTSUITE_API_URL`
- `SMARTSUITE_TIMEOUT_SECONDS`
- `RER_MFA_MAX_RETRIES`
- `RER_MFA_WAIT_SECONDS`
- `PLAYWRIGHT_HEADLESS`

## Troubleshooting

- `403` or API Gateway auth failure: check the `x-api-key` value.
- Repeated `202` responses: refresh or MFA is still in progress; retry after a short delay.
- Lambda failure during refresh: check SmartSuite config, Gmail token, Playwright runtime, and RER credentials.
