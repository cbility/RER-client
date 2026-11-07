# RER client

Python 3.12+ client and AWS Lambda services for the Ofgem Renewable Electricity
Register (RER). RER serves HTML: this project makes authenticated requests and
parses responses into typed Python objects.

## Architecture

| Component | Responsibility |
| --- | --- |
| [RERClient](src/rer_client/client.py) and [parsers](src/rer_client/parsing.py) | Request RER pages and parse users, organisations, stations, certificates and output submissions. Response models live in [models.py](src/rer_client/models.py). |
| [Scraper function](src/rer_scraper/handler.py) | Read pending work from SmartSuite, obtain cookies from the auth API, fetch/parse RER data through `RERClient`, and synchronise records back to SmartSuite. |
| [Session-auth function](session_auth/rer_session_auth/handler.py) | Validate stored cookies, perform browser login/MFA when necessary, and save refreshed cookies to SmartSuite. |

The [SAM template](template.yaml) deploys **two** API Gateway endpoints:

- **Scraper:** `POST /` — runs pending scraper work.
- **Session auth:** `GET /` — returns cookies, or starts a background refresh.

Both require their own `x-api-key`. There is no separate client/proxy API in this
template. HTTP clients call the scraper directly; they do **not** need to obtain
or forward RER cookies. No scheduled trigger is defined in the template: an
external caller must invoke the scraper.

## Installation

Run commands from the repository root. Install [uv](https://docs.astral.sh/uv/),
then install the package and development dependencies:

```powershell
uv sync
```

To install the library in another project:

```powershell
uv add git+https://github.com/cbility/RER-API-wrapper.git
```

### Local configuration

Keep local values in an ignored `.env` file:

```dotenv
SMARTSUITE_API_TOKEN=...
SMARTSUITE_ACCOUNT_ID=...
RER_SESSION_AUTH_API_URL=https://YOUR_AUTH_API_ID.execute-api.eu-west-2.amazonaws.com/Prod/
RER_SESSION_AUTH_API_KEY_VALUE=...
SMARTSUITE_TABLE_ID=...
SMARTSUITE_RECORD_ID=...
SMARTSUITE_COOKIES_FIELD=...
MAKE_API_KEY=...
```

- The scraper needs the first four values. It currently uses a login record ID
  defined in `build_service()` and table/job IDs defined in
  [smartsuite.py](src/rer_scraper/smartsuite.py); these are not all configurable
  through environment variables.
- Auth needs the SmartSuite token, account, table, record and cookie-field values.
  It reads the RER email/password from fields `sb966ee382` and `sb4e5173b6` on that
  record, not from `RER_EMAIL`/`RER_PASSWORD` environment variables.
- `MAKE_API_KEY` is used by the auth MFA email retrieval integration. Optional
  settings include `SMARTSUITE_REFRESHED_AT_FIELD`, `SMARTSUITE_TIMEOUT_SECONDS`,
  `PLAYWRIGHT_HEADLESS`, `RER_MFA_MAX_RETRIES`, `RER_MFA_WAIT_SECONDS` and `LOG_LEVEL`.

The separate [cookie bootstrap helper](test/bootstrap_rer_cookies.py) uses
`RER_EMAIL` and `RER_PASSWORD` and saves local cookies to `rer_cookies.json`.
That file is for development/fixture tools; deployed functions use SmartSuite.

## Calling the scraper over HTTP

### Find the URL and API key

Get `RERScraperApiUrl` from the deployed CloudFormation stack:

```powershell
aws cloudformation describe-stacks --stack-name rer-client --region eu-west-2 --query "Stacks[0].Outputs[?OutputKey=='RERScraperApiUrl'].OutputValue" --output text --no-cli-pager
```

In API Gateway, obtain the **value** of the `RERScraperApiKey` resource and ensure
it is associated with the scraper usage plan. Use the scraper key, not the auth
key. Store the URL and key securely in the calling application's environment,
for example `RER_SCRAPER_API_URL` and `RER_SCRAPER_API_KEY_VALUE`.

### Request examples

A body is not required. From PowerShell, using `curl.exe`:

```powershell
curl.exe -i -X POST -H "x-api-key: $env:RER_SCRAPER_API_KEY_VALUE" "$env:RER_SCRAPER_API_URL"
```

To restrict a refresh to one organisation and its stations:

```powershell
curl.exe -i -X POST -H "x-api-key: $env:RER_SCRAPER_API_KEY_VALUE" "${env:RER_SCRAPER_API_URL}?organisation_reference=GEN0191576"
```

Python client example:

```python
import os

import requests

response = requests.post(
    os.environ["RER_SCRAPER_API_URL"],
    headers={"x-api-key": os.environ["RER_SCRAPER_API_KEY_VALUE"]},
    params={"organisation_reference": "GEN0191576"},  # Omit for all organisations.
    timeout=60,
)
response.raise_for_status()
if response.status_code == 204:
    print("No pending work")
elif response.status_code == 202:
    print("Waiting for session refresh; a background retry was scheduled")
else:
    print(response.json())
```

A targeted request still checks SmartSuite for pending work; it does not force a
refresh. It skips the shared RER user-record update. The handler reads
`organisation_reference` from the query string, not a JSON body.

### Responses and execution behaviour

| Status | Meaning |
| --- | --- |
| `200` | Pending work completed. The current result envelope is `{"refresh_result": null, "transfer_results": []}`; it is not an export of the fetched RER records. Refresh writes go to SmartSuite. |
| `202` | Auth cookies are being refreshed. Body: `{"status":"waiting_for_session_refresh"}`. The scraper schedules an asynchronous self-invocation; Lambda may retry that invocation up to twice if the session remains unavailable. |
| `204` | No pending SmartSuite operations. No response body. |

**HTTP calls perform real SmartSuite writes.** There is no HTTP dry-run parameter.
`refresh_data` is implemented; a pending `transfer_certificates` operation
currently raises `NotImplementedError`. Missing/invalid API keys are normally
rejected by API Gateway with `403`; unhandled Lambda errors can appear as `502`.

The initial scrape is synchronous. The Lambda timeout is 300 seconds, but API
Gateway's integration timeout can be shorter (the inspected deployment used
29 seconds). A client timeout or gateway timeout does not necessarily stop the
Lambda, so check CloudWatch before repeating a request to avoid duplicate work.
Increasing the client-side timeout alone cannot increase the gateway timeout.
There is currently no job-status/polling endpoint. CORS is not configured in the
template; browser clients need additional configuration or a server-side caller.

### Session-auth API

Internal callers use `GET` on the `RERSessionAuthApiUrl` stack output with the
session-auth API key:

```powershell
curl.exe -i -H "x-api-key: $env:RER_SESSION_AUTH_API_KEY_VALUE" "$env:RER_SESSION_AUTH_API_URL"
```

It returns `200` with `{"cookies": {...}}` when cookies are valid, or `202` with a
message while refreshing them asynchronously. Treat returned cookies as secrets.
The scraper already performs this step internally.

## Testing and local handler debugging

### Offline tests

The actual handler/local-entry-point tests are in
[test_targeted_scrape.py](test/rer-scraper/test_targeted_scrape.py). They use mocks
and cover query forwarding, inline local execution, targeted retry behaviour,
organisation filtering, and the configured SmartSuite login-record ID.
[Service tests](test/rer-scraper/test_service.py) cover no-work exits, retry
scheduling and certificate-transfer preparation.

```powershell
uv run pytest test\rer-scraper\test_targeted_scrape.py test\rer-scraper\test_service.py -v
uv run pytest test\session_auth\test_store.py -v
```

The auth store tests stub HTTP access; they are not end-to-end auth handler tests.
There are no `test_lambda_handler.py` or `test_scraper_handler.py` files in the
current tree.

### Run the real scraper handler locally

```powershell
uv run python -m rer_scraper.handler
```

The testing section at the end of [handler.py](src/rer_scraper/handler.py):

- Loads `.env` and calls the real `handler()` with a local context.
- Sets `dry_run=True`, so SmartSuite mappings run but writes are skipped.
- Uses the existing `retry_scrape` branch with `schedule_retry=False` so execution
  stays in the local process without invoking AWS Lambda.
- Still reads **live** SmartSuite operations and calls the deployed auth API and
  RER. No pending operations means no scrape; pending auth refresh raises
  `SessionRefreshPending`, so rerun once cookies are ready. Calling the auth API
  can itself trigger a deployed cookie refresh.
- Normally prints `None` on successful completion of this retry branch; use logs
  and breakpoints to inspect the fetched data.

Use the repository's `.venv` interpreter in VS Code and set breakpoints in the
handler, service, client or parsers. Run/debug the handler file, or configure the
Python debugger with module `rer_scraper.handler` and the repository root as its
working directory. Do not use `--no-dry-run` with this module: despite its startup
log mentioning that flag, the local entry point does not parse command-line
arguments. To deliberately enable writes, change the testing-section call to
`dry_run=False` after checking the configured account.

`python -m rer_scraper.handler` can emit a `runpy` warning because
[rer_scraper/__init__.py](src/rer_scraper/__init__.py) imports the handler before
Python executes it as `__main__`. This is an import-order issue, not a scrape
failure; it can occur in a fresh process too. Running the file directly avoids
that particular module-execution pattern. No warning suppression is required.

### Run the real auth handler locally

Install the local browser once, then run the module with `.env` loaded explicitly:

```powershell
uv run playwright install chromium
uv run --env-file .env python -m rer_session_auth.handler
```

The testing section in [auth handler.py](session_auth/rer_session_auth/handler.py)
calls `handler({"refresh_cookies": True}, context)` directly: it performs a fresh
login/MFA flow inline and **writes refreshed cookies to SmartSuite**. It is not a
dry run, and does not merely validate the existing cookies. It sets visible
browser mode and `RER_LOCAL_TEST`; the latter selects the code's test recipient
for failure notifications, not an offline/mock mode. The script does not load
`.env` itself, hence `uv run --env-file` above. Set breakpoints and run/debug the
file in VS Code with the same environment to step through the live auth path.

### Cached HTML and live tests

Most tests under [test/rer-python](test/rer-python) use `CachedRERClient` from the
current [conftest.py](test/rer-python/conftest.py), reading
`test/rer-html/snapshots/latest/`. They require fixtures on disk, not live cookies
for every run. In particular, the cached scraper integration test uses the real
service/mapping code with mocked operation selection and cached RER responses:

```powershell
uv run pytest test\rer-python -v
uv run pytest test\rer-python\test_scraper_all_cached.py -v -s
```

Run the `rer-python` and `rer-scraper` directories separately: both conftest files
register `--dry-run`/`--no-dry-run`, so collecting both together can produce a
duplicate-option error. Those pytest flags are distinct from the local handler
entry point. Do not assume every test is offline or safe to run with real
credentials: inspect live test files before running them, and do not enable
`--no-dry-run` unless real writes are intended.

Examples of live coverage:

- [test_live_scraper.py](test/rer-scraper/test_live_scraper.py) calls the deployed
  auth API and live RER, forces `refresh_data` through mocked operation selection,
  and uses the dry-run fixture by default.
- [test_live_smartsuite.py](test/rer-scraper/test_live_smartsuite.py) runs a live
  operations query only when `RUN_LIVE_SMARTSUITE_TESTS=1` is set.
- [test_store_live.py](test/session_auth/test_store_live.py) can modify stored
  cookie fields and trigger auth refreshes; it is not an offline handler test.

To regenerate HTML snapshots, first obtain valid development cookies, then fetch
and select a snapshot:

```powershell
uv run python test\bootstrap_rer_cookies.py
uv run python test\rer-html\fetch_all_snapshots.py
uv run python test\rer-python\manage_cache.py latest
uv run python test\rer-python\manage_cache.py status
```

See [HTML fixture documentation](test/rer-html/README.md). Snapshot generation
contacts RER and writes local HTML; keep cookies and account data private.

## Build and deploy

Requires Docker running, AWS CLI authentication, and SAM CLI. The default stack
is `rer-client` in `eu-west-2`, configured in [samconfig.toml](samconfig.toml).
Use the existing PowerShell deployment script from the repository root:

```powershell
aws login
aws configure set region eu-west-2
. .\.venv\Scripts\Activate.ps1
. .\.envrc.ps1
.\scripts\deploy.ps1
```

[deploy.ps1](scripts/deploy.ps1) requires `SMARTSUITE_API_TOKEN`,
`RER_SESSION_AUTH_API_KEY_VALUE` and `MAKE_API_KEY` in the process environment.
It builds the pinned SmartSuite dependency wheel, runs `sam build`, and runs
`sam deploy` with those parameter values. It does not automatically copy every
`.env` variable to Lambda.

- Auth is a Playwright container image, installing
  [session_auth/requirements.txt](session_auth/requirements.txt), including OpenAI.
- Scraper is a Python 3.12 zip deployment using
  [src/requirements.txt](src/requirements.txt); OpenAI is not a scraper deployment
  dependency. The root development environment includes dependencies for both.
- The template supplies the scraper's auth URL using a CloudFormation reference.
  Retrieve current URLs from stack outputs instead of hardcoding API IDs.
- API Gateway generates the API key resources. The scraper's configured outbound
  auth key (`SessionAuthApiKeyValue`) must match the actual session-auth API key
  value; that parameter does not set the generated key's value.

Review account/table/record settings in the template before deploying elsewhere.
The optional [auth](scripts/sync-session-auth-env.sh) and
[scraper](scripts/sync-scraper-env.sh) environment-sync scripts are Bash tools,
not part of `deploy.ps1`. They replace the function's environment-variable map;
review their contents before use so additional settings are not lost. The auth
sync script still requires `RER_EMAIL` and `RER_PASSWORD`, although the current
handler reads login credentials from SmartSuite. Manual environment changes may
also be overwritten by later SAM deployments.

For failures, inspect the deployed function's CloudWatch logs. Both Lambdas have
300-second timeouts; the scraper can spend several minutes fetching data before
writing it. A `502` from auth can mean an import/runtime error, not a bad URL.

## Direct Python library use

The library accepts existing cookies and validates them during construction:

```python
from rer_client import RERClient

client = RERClient(auth_cookies={"cookie-name": "cookie-value"})
user = client.get_user()
organisations = client.get_user_organisations()
if organisations:
    organisation_id = organisations[0].organisation_id
    details = client.get_organisation_detail(organisation_id)
    stations = client.get_organisation_stations(organisation_id)
    certificates = client.get_organisation_certificates(organisation_id)
    output_data = client.get_organisation_output_data(organisation_id)
```

Use attributes on response models, not dictionary subscripting. Additional
methods include certificate breakdown/history, output-data tasks and station
declarations; consult
[client.py](src/rer_client/client.py) for current signatures.

## Limitations and sensitive data

- This is an unofficial integration, not supported by Ofgem. HTML changes can
  break parsers and authentication depends on external services.
- Certificate transfer execution is not implemented in the scraper workflow.
- Treat API keys, `.env`, RER cookies, SmartSuite records and downloaded HTML as
  sensitive. `.env` and `rer_cookies.json` are ignored; do not commit them.
- Debug/error logs can include account or record data. Avoid sharing them without
  redaction. Do not place API keys in query strings or public browser code.