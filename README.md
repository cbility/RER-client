# RER client

Python package for wrapping the Ofgem Renewable Electricity Register (RER) portal. The RER site returns HTML, so this package handles authenticated requests, parses the relevant pages, and returns typed Python objects.

The repository includes:
- **RERClient**: Core library for interacting with the RER portal (used by the Scraper Lambda)
- **Session Auth Lambda**: Manages RER login, MFA, cookie validation, and SmartSuite-backed cookie storage
- **Scraper Lambda**: Scheduled job that syncs RER data to SmartSuite

Deployed API usage is documented in [`docs/session-auth-api.md`](docs/session-auth-api.md).
Scraper usage is documented in [`docs/scraper-api.md`](docs/scraper-api.md).

## Installation

```bash
uv sync
```

Install from Git in another repo with:

```bash
uv add git+https://github.com/ORG/RER-client.git
```

## Build and Deploy

The session-auth Lambda is deployed as a Docker image, so Docker, AWS CLI, and
SAM CLI must be installed and configured for the `eu-west-2` region.

Create a local `.env` file with the deployment values. It must include:

```dotenv
RER_EMAIL=...
RER_PASSWORD=...
SMARTSUITE_API_TOKEN=...
SMARTSUITE_ACCOUNT_ID=...
SMARTSUITE_TABLE_ID=...
SMARTSUITE_RECORD_ID=...
SMARTSUITE_COOKIES_FIELD=...
```

Keep `.env` out of version control. Build the Lambda image without using a stale
dependency cache, then deploy the infrastructure and synchronize the Lambda
environment separately:

```bash
sam build --no-cached
sam deploy
./scripts/sync-session-auth-env.sh
```

Run `sam deploy` after code or infrastructure changes. Run
`./scripts/sync-session-auth-env.sh` after every deployment and whenever `.env`
values change. The sync script updates the Lambda environment through the AWS CLI structured JSON API.

The scraper Lambda requires separate configuration after deployment:

```bash
./scripts/sync-scraper-env.sh
```

## Getting started

To use the package you need authenticated RER cookies. The helper script at `test/bootstrap_rer_cookies.py` can regenerate local cookies for development.


### Use the RERClient

```python
from rer_client import RERClient

cookies = {"cookie-name": "cookie-value"}
client = RERClient(auth_cookies=cookies)

user = client.get_user()
print(f"Logged in as: {user.full_name}")

organisations = client.get_user_organisations()
for org in organisations:
    print(f"  - {org.name} ({org.organisation_id})")
```

## Testing

The test suite uses cached HTML responses stored in `test/rer-html/snapshots/latest/`. This allows tests to run offline without depending on the RER portal being available.

**Run tests:**
```bash
uv run pytest test/rer-python/ -v
```

**Update cache fixtures:**
```bash
# Fetch fresh HTML from RER portal (requires valid cookies)
uv run python test/rer-html/fetch_all_snapshots.py

# Set as latest cache
uv run python test/rer-python/manage_cache.py latest
```

**Cache management:**
```bash
# Check cache status
uv run python test/rer-python/manage_cache.py status

# Clean old snapshots (older than 7 days)
uv run python test/rer-python/manage_cache.py clean --older-than 7d
```

See `test/rer-html/README.md` for more details on HTML snapshots.

### Lambda Handler Integration Tests

#### client Handler Tests

The `test/rer-python/test_lambda_handler.py` file contains integration tests for the **client Lambda handler** using cached HTML. These tests exercise the full handler workflow without making live requests to the RER portal or writing to SmartSuite.

#### Scraper Handler Tests

The `test/rer-python/test_scraper_handler.py` file contains integration tests for the **Scraper Lambda handler** with mocked SmartSuite operations. These tests verify the scraper workflow with different SmartSuite configurations.

**Run Scraper tests:**
```bash
# Run all Scraper handler tests
uv run pytest test/rer-python/test_scraper_handler.py -v

# Run specific scenario
uv run pytest test/rer-python/test_scraper_handler.py::TestScraperHandlerRefreshData -v
```

**What's tested:**
- Real `handler()` function from `rer_scraper/handler.py`
- Real `RERScraperService` class
- Mocked SmartSuite responses (configurable operations)
- Cached HTML for RER requests
- Different scenarios:
  - No operations (returns 204)
  - `refresh_data` operation (scrapes RER, updates SmartSuite)
  - Session refresh pending (returns 202, schedules retry)
  - Retry event execution

**Mocking SmartSuite operations:**
```python
# In test fixture
mock_smartsuite = MockSmartSuiteClient("test", "test")
mock_smartsuite.set_operations(["refresh_data"])  # or ["transfer_certificates"]
mock_smartsuite.set_current_organisations([...])  # existing records
```

#### Scraper Integration Tests with Cached Data

The `test/rer-python/test_scraper_all_cached.py` file contains integration tests that run the **actual Scraper service** against ALL cached HTML data. These tests validate the full scraping and parsing logic with real data volume.

**Run cached data tests:**
```bash
# Run all cached data tests with logging
uv run pytest test/rer-python/test_scraper_all_cached.py -v -s --log-cli-level=INFO

# Run specific test
uv run pytest test/rer-python/test_scraper_all_cached.py::TestScraperAllCachedData::test_scrape_all_organisations -v -s

# Run individual organisation tests (one per cached org)
uv run pytest test/rer-python/test_scraper_all_cached.py::TestScraperAllCachedData::test_individual_organisation_scrape -v -s
```

**Features:**
- ✅ Real `RERScraperService` class (not mocked)
- ✅ Real `RERSmartSuiteClient.map_organisation()` method
- ✅ `CachedRERClient` for all RER API calls (uses cached HTML)
- ✅ ALL cached organisations from `test/rer-html/snapshots/latest/`
- ✅ Full logging output showing organisations to create/update
- ✅ `dry_run` mode enabled by default (no SmartSuite writes)

**SmartSuite Logging:**

The `RERSmartSuiteClient` class includes comprehensive logging for all SmartSuite operations:

- **INFO level**: Shows number of records being updated/created and success confirmation
- **DEBUG level**: Shows full record data being sent to SmartSuite
- **ERROR level**: Shows failure details including exception message and failed records

Example output:
```
INFO - Updating 20 organisation(s) in SmartSuite...
DEBUG - Organisations to create: [{'sde6082ea0': 'Org Name', ...}]
INFO - ✓ Successfully created 20 organisation(s)
```

On error:
```
ERROR - ✗ Failed to create organisations: SmartSuite API error: ...
ERROR - Failed records: [{'sde6082ea0': 'Org Name', ...}]
```

**Demo scripts:**
```bash
# See SmartSuite logging in action
uv run python test/rer-python/demo_smartsuite_logging.py

# See error handling logging
uv run python test/rer-python/demo_smartsuite_errors.py
```

**Dry Run Mode:**

The tests use `dry_run=True` by default to prevent accidental writes to SmartSuite. When `dry_run=True`:
- The scraper processes all organisations normally
- SmartSuite mapping is performed using the **REAL** `RERSmartSuiteClient.map_organisation()` method
- Logs show all organisations that would be created/updated
- **No actual writes** are made to SmartSuite (the service skips them)

**Important:** The tests use the **real** `RERSmartSuiteClient` class with NO mocking of the mapping or update methods. Only `get_operations()` is mocked to return test data (prevents querying SmartSuite for test configuration). This means:
- ✅ Real `map_organisation()` method is tested
- ✅ Real `update_organisations()` method is called (but skipped when `dry_run=True`)
- ✅ Real `create_organisations()` method is called (but skipped when `dry_run=True`)
- ✅ Full code path is tested

To **disable dry run** and test actual SmartSuite integration:

1. **In test code**: Edit `test/rer-python/test_scraper_all_cached.py` and change:
   ```python
   service = RERScraperService(
       smartsuite=real_smartsuite,  # Real SmartSuite client
       # ... other params ...
       dry_run=False  # Change from True to False
   )
   ```

2. **Provide real credentials**: Set environment variables or update the fixture:
   ```bash
   export SMARTSUITE_ACCOUNT_ID="your-account-id"
   export SMARTSUITE_API_TOKEN="your-api-token"
   ```

3. **Run the test**:
   ```bash
   uv run pytest test/rer-python/test_scraper_all_cached.py -v -s
   ```

⚠️ **Warning**: Running with `dry_run=False` will make **real changes** to your SmartSuite account!

**Example output with dry_run enabled:**
```
INFO - Found 0 orgs to be updated and 20 to be created
INFO - Organisations to CREATE:
INFO -   {'sde6082ea0': 'Richard Maxwell Ltd', 's44395f753': 'GEN0215344', 's90b4a920a': 'Generator', 'sf3acd7357': 'Approved'}
INFO -   {'sde6082ea0': 'AMP Heat Limited', 's44395f753': 'GEN0208381', 's90b4a920a': 'Generator', 'sf3acd7357': 'Approved'}
...
INFO - Dry run mode: skipping SmartSuite writes
```

This shows exactly what would be sent to SmartSuite without making any actual changes.

**Dry run mode:**
By default, tests run with SmartSuite writes disabled (operations are tracked but not executed). This allows testing the full workflow without modifying production data.

See the individual test files for detailed documentation and examples.

## RERClient Methods

The `RERClient` class provides direct access to RER portal data:

- `get_user()` - User dashboard
- `get_user_organisations()` - List of organisations
- `get_organisation(organisation_id)` - Organisation details
- `get_organisation_stations(organisation_id)` - Stations list
- `get_organisation_certificates(organisation_id)` - Certificates overview
- `get_organisation_output_data_tasks(organisation_id)` - Output data tasks
- `get_station(station_id)` - Station details

## Example: Get Organisation Data

```python
from rer_client import RERClient

cookies = {"cookie-name": "cookie-value"}
client = RERClient(auth_cookies=cookies)

org_id = "GEN0215941"
organisations = client.get_user_organisations()
stations = client.get_organisation_stations(org_id)
certificates = client.get_organisation_certificates(org_id)
```

## Security

- Store credentials securely (use environment variables)
- Send an `x-api-key` header when calling the session-auth API
- Don't commit `rer_cookies.json` to version control
- Cookies grant full account access - treat like passwords
- Add `rer_cookies.json` to your `.gitignore`

## Session Auth Lambda

- Source lives in `session_auth/`
- It is deployed as a separate API Gateway endpoint and Lambda function
- `RERSessionAuthFunction` is packaged as a Lambda container image so Playwright/Chromium is available at runtime
- It loads cached cookies from a SmartSuite record using `Authorization: Token ...` plus the `ACCOUNT-ID` workspace header
- Configure `SMARTSUITE_ACCOUNT_ID`, `SMARTSUITE_TABLE_ID`, `SMARTSUITE_RECORD_ID`, and `SMARTSUITE_COOKIES_FIELD` in the auth Lambda environment
- If cached cookies are invalid, it starts the Playwright + Gmail MFA flow asynchronously and returns `202 Accepted`; the refreshed cookies are saved to SmartSuite for a later request
- Local SAM build/deploy of the auth Lambda image requires Docker so the image can be built and pushed to ECR

## Session Auth API

Use the separate session-auth API to obtain RER cookies before calling the client API.

1. Get the deployed base URL from the CloudFormation output `RERSessionAuthApiUrl`.
2. Get the API key value for `RERSessionAuthApiKey` from API Gateway.
3. Call the session-auth API root. It returns `200` with cached cookies or `202` while refreshing them.
4. Send returned cookies to the client API.

Notes:
- A `202` response means refresh is running in the background; retry after a short delay.
- The client API is separate and requires its own API key.

Example:

```bash
curl \
  -H "x-api-key: YOUR_SESSION_AUTH_API_KEY" \
  "https://YOUR_SESSION_AUTH_API_ID.execute-api.eu-west-2.amazonaws.com/Prod/"
```

More examples and supported routes are in [`docs/session-auth-api.md`](docs/session-auth-api.md).

## Limitations

- Subject to website changes breaking the client
- This is an unofficial library with no support from Ofgem
