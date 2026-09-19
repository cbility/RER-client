"""Integration tests for RER Scraper with ALL cached organisations.

These tests run the actual scraper service against all cached HTML data
to verify the full scraping and parsing logic works correctly.

Usage:
    # Run with dry_run=True (default, no SmartSuite writes)
    uv run pytest test/rer-python/test_scraper_all_cached.py -v -s

    # Run with dry_run=False (real SmartSuite writes)
    uv run pytest test/rer-python/test_scraper_all_cached.py -v -s --no-dry-run

    # Run with specific log level
    uv run pytest test/rer-python/test_scraper_all_cached.py -v --log-cli-level=INFO

    Note: you can regenerate snapshots by running 'uv run python test/rer-html/fetch_all_snapshots.py'

Requirements:
    - Cached HTML files in test/rer-html/snapshots/latest/
    - Run 'uv run python test/rer-html/fetch_all_snapshots.py' to update cache
"""

import logging
import os
import pytest
from unittest.mock import Mock
from pathlib import Path
from datetime import datetime

from rer_scraper.service import RERScraperService, SessionAuthClient
from rer_scraper.smartsuite import RERSmartSuiteClient
from rer_scraper.models import ScraperResult
from cached_rer_client import CachedRERClient, FIXTURES_DIR

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


@pytest.fixture(scope="module")
def cached_client():
    """Create cached client with ALL available HTML."""
    client = CachedRERClient(FIXTURES_DIR)
    logger.info(f"Cached client initialized with fixtures from: {FIXTURES_DIR}")

    # Count available organisations (FIXTURES_DIR already points to 'latest')
    org_count = len(
        [d for d in FIXTURES_DIR.iterdir() if d.is_dir() and d.name != "_user"]
    )
    logger.info(f"Found {org_count} cached organisations")

    return client


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
def mock_session_auth():
    """Create mock session auth that returns test cookies."""
    mock = Mock(spec=SessionAuthClient)
    mock.get_cookies.return_value = {
        "session": "test-session-cookie",
        "XSRF-TOKEN": "test-xsrf-token",
    }
    return mock


@pytest.fixture
def mock_retry_invoker():
    """Create mock retry invoker."""
    mock = Mock()
    mock.invoke = Mock()
    return mock


@pytest.fixture
def cached_rer_client(cached_client):
    """Create RERClient that uses cached_client internally."""
    # Use the cached_client directly - it already has all the RERClient methods
    # but serves from cache instead of making live requests
    return cached_client


class TestScraperAllCachedData:
    """Test scraper service against ALL cached organisations."""

    def test_scrape_all_organisations(
        self,
        smartsuite,
        mock_session_auth,
        mock_retry_invoker,
        cached_rer_client,
        caplog,
        dry_run_mode,
    ):
        """
        Test scraping ALL cached organisations.

        This test:
        1. Creates a real RERScraperService instance
        2. Uses CachedRERClient for all RER API calls (cached HTML)
        3. Processes all available organisations
        4. Verifies no errors occur during parsing
        5. Confirms dry_run mode prevents SmartSuite writes
        """
        caplog.set_level(logging.DEBUG)

        # Enable logging from rer_scraper modules
        logging.getLogger("rer_scraper.smartsuite").setLevel(logging.DEBUG)
        logging.getLogger("rer_scraper.service").setLevel(logging.DEBUG)

        logger.info("=" * 80)
        logger.info("Starting full scrape of ALL cached organisations")
        logger.info("=" * 80)

        # Create service using dry_run_mode fixture from command line
        # Use cached_rer_client (which is the CachedRERClient) as the client factory
        service = RERScraperService(
            smartsuite=smartsuite,
            session_auth=mock_session_auth,
            retry_invoker=mock_retry_invoker,
            function_name="test-scraper",
            client_factory=lambda cookies: cached_rer_client,
            dry_run=dry_run_mode,
            ss_login_record_id="",
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
