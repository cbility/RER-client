"""Shared setup for RER scraper integration tests."""

import pytest


def pytest_addoption(parser):
    """Add custom command-line options for tests."""
    parser.addoption(
        "--dry-run",
        action="store_true",
        default=True,
        help="Enable dry_run mode (default: True, no SmartSuite writes)",
    )
    parser.addoption(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Disable dry_run mode (real SmartSuite writes)",
    )


@pytest.fixture(scope="session")
def dry_run_mode(request):
    """Get dry_run setting from command line."""
    return request.config.getoption("--dry-run")
