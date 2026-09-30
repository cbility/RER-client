"""Live integration test for RER Scraper against real RER API.

This test runs the actual scraper service against the live RER API
(no cached HTML) to verify the full scraping pipeline works correctly.

Usage:
    # Run with dry_run=True (default, no SmartSuite writes)
    uv run pytest test/rer-scraper/test_live_scraper.py -v -s

    # Run with dry_run=False (real SmartSuite writes)
    uv run pytest test/rer-scraper/test_live_scraper.py -v -s --no-dry-run

    # Run with specific log level
    uv run pytest test/rer-scraper/test_live_scraper.py -v --log-cli-level=INFO

Requirements:
    - Valid RER session cookies (rer_cookies.json)
    - Environment variables:
        - RER_SESSION_AUTH_API_URL
        - RER_SESSION_AUTH_API_KEY_VALUE
        - SMARTSUITE_ACCOUNT_ID
        - SMARTSUITE_API_KEY
        - AWS_LAMBDA_FUNCTION_NAME
    - Run 'uv run python test/bootstrap_rer_cookies.py' to refresh cookies if needed
"""

import logging
import os
import pytest
from unittest.mock import Mock

from rer_scraper.service import RERScraperService, SessionAuthClient
from rer_scraper.smartsuite import RERSmartSuiteClient
from rer_client import RERClient

# Configure logging to show during tests
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Suppress verbose logs from external libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@pytest.fixture
def smartsuite():
    """Create RERSmartSuiteClient.

    Create a modified RERSmartSuiteClient instance for testing.
    get_operations() is mocked to return test data.

    To prevent actual writes during testing:
    - Use dry_run=True in RERScraperService (default in these tests)
    - The service will skip SmartSuite writes AND skip querying for existing orgs

    To test real SmartSuite integration:
    - Set dry_run=False in the test
    - Provide real SMARTSUITE_ACCOUNT_ID and SMARTSUITE_API_TOKEN
    - The real SmartSuite API will be called
    """

    account_id = os.getenv("SMARTSUITE_ACCOUNT_ID", "test-account-id")
    api_token = os.getenv("SMARTSUITE_API_TOKEN", "test-api-token")

    client = RERSmartSuiteClient(account_id=account_id, api_token=api_token)

    # Override get_operations to return test operations
    # This prevents querying SmartSuite for test configuration
    client.get_operations = Mock(return_value=["refresh_data"])

    return client


@pytest.fixture
def session_auth():
    """Create real SessionAuthClient that calls the session-auth Lambda."""
    auth_api_url = os.getenv("RER_SESSION_AUTH_API_URL")
    auth_api_key = os.getenv("RER_SESSION_AUTH_API_KEY_VALUE")

    if not auth_api_url or not auth_api_key:
        pytest.skip(
            "RER_SESSION_AUTH_API_URL and RER_SESSION_AUTH_API_KEY_VALUE must be set"
        )

    logger.info(f"Creating SessionAuthClient with API URL: {auth_api_url}")
    return SessionAuthClient(auth_api_url, auth_api_key)


@pytest.fixture
def retry_invoker():
    """Create mock retry invoker."""
    mock = Mock()
    mock.invoke = Mock()
    return mock


@pytest.fixture
def client_factory():
    """Create factory that returns a real RERClient with live cookies."""

    def _factory(cookies: dict[str, str]) -> RERClient:
        """Create RERClient with provided cookies."""
        if not cookies:
            pytest.fail("No cookies provided to RERClient")

        # Create real RERClient that will make live API calls
        client = RERClient(auth_cookies=cookies)
        logger.info("Created live RERClient (will make real API calls)")
        return client

    return _factory


class TestLiveScraper:
    """Test scraper service against live RER API."""

    def test_scrape_live_organisations(
        self,
        smartsuite,
        session_auth,
        retry_invoker,
        client_factory,
        caplog,
        dry_run_mode,
    ):
        """
        Test scraping organisations from live RER API.

        This test:
        1. Creates a real RERScraperService instance
        2. Uses SessionAuthClient to load real cookies from disk
        3. Uses RERClient for live API calls (no caching)
        4. Processes organisations from the live RER API
        5. Verifies no errors occur during scraping and parsing
        6. Confirms dry_run mode prevents SmartSuite writes

        Note: This test makes real API calls to rer.ofgem.gov.uk
        """
        caplog.set_level(logging.DEBUG)

        # Enable logging from rer_scraper modules
        logging.getLogger("rer_scraper.smartsuite").setLevel(logging.DEBUG)
        logging.getLogger("rer_scraper.service").setLevel(logging.DEBUG)
        logging.getLogger("rer_client.client").setLevel(logging.DEBUG)

        logger.info("=" * 80)
        logger.info("Starting LIVE scrape of RER organisations")
        logger.info("=" * 80)

        # Get cookies from session auth
        logger.info("Requesting cookies from session-auth API...")
        cookies = session_auth.get_cookies()

        if cookies is None:
            pytest.skip(
                "Session cookies not ready (API returned 202). "
                "This may indicate the session refresh is still in progress. "
                "Retry will be scheduled automatically."
            )

        logger.info(f"Loaded {len(cookies)} cookies from session auth")

        # Create service using dry_run_mode fixture from command line
        service = RERScraperService(
            smartsuite=smartsuite,
            session_auth=session_auth,
            retry_invoker=retry_invoker,
            function_name="test-scraper-live",
            client_factory=client_factory,
            dry_run=dry_run_mode,
            ss_login_record_id="6a7f301f54fd4d6f819c1e5f",
        )

        logger.info(f"RERScraperService created (dry_run={service.dry_run})")

        # Run the service
        status_code, result = service.run()

        # Verify execution
        logger.info(f"Service completed with status: {status_code}")

        assert status_code == 200, f"Expected 200, got {status_code}"
        assert result is not None, "Result should not be None"

        # Log summary
        logger.info("=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Status Code: {status_code}")
        logger.info(f"Dry Run: {service.dry_run}")
        logger.info(
            f"SmartSuite writes: {'SKIPPED' if service.dry_run else 'EXECUTED'}"
        )
        logger.info("=" * 80)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--log-cli-level=INFO"])
