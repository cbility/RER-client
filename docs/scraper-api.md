# RER Scraper API

## Local debugging

From the repository root, run `uv run python -m rer_scraper.handler`, or debug
`src/rer_scraper/handler.py` in VS Code. The testing section loads `.env` and calls
the real handler with `dry_run=True`: it reads live SmartSuite operations and RER
data but skips SmartSuite writes and AWS retries. If there is no scheduled work,
it exits without scraping. If session refresh is pending, it raises
`SessionRefreshPending`; rerun once the session is ready.

## API behavior

`POST /` starts RER scraper work. Without an organisation reference, the scraper
reads operations from SmartSuite and exits with `204 No Content` when there is
no work.

To force a refresh of one organisation and its stations, include its RER reference
as a query parameter, for example: `POST /?organisation_reference=GEN0191576`.
Targeted requests bypass the pending-work table, including on retries, and log
the organisation reference at the start. They do not update the RER user record.

When the session-auth API returns `202 Accepted`, the scraper returns:

```json
{"status":"waiting_for_session_refresh"}
```

It also schedules one asynchronous retry. Lambda retries that asynchronous
invocation up to two times while the session refresh remains in progress.

The refresh path enumerates accessible organisations, stations, station details,
certificate summaries, and station-matching certificate breakdowns. SmartSuite
schema mappings for operation records and refreshed data are intentionally not
configured yet.

Transfer preparation uses inclusive `Mon YYYY` periods and selects all matching
certificate ranges for the source station. A range with no matching certificates
is a successful no-op. The scraper does not submit final certificate transfers.

Deploy infrastructure with `sam deploy`, then configure the scraper environment:

```bash
./scripts/sync-scraper-env.sh
```

The sync script reads `RER_SESSION_AUTH_API_URL`,
`RER_SESSION_AUTH_API_KEY_VALUE`, `SMARTSUITE_API_TOKEN`, and
`SMARTSUITE_ACCOUNT_ID` from `.env`.