"""Live output test for RERScraperService.refresh_data()."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from rer_client import RERClient
from rer_scraper.models import ScraperOperations
from rer_scraper.service import RERScraperService

REPO_ROOT = Path(__file__).resolve().parents[2]
COOKIES_FILE = REPO_ROOT / "rer_cookies.json"


class StubSmartSuiteClient:
    def get_operations(self, launch_time) -> list[str]:
        return ["refresh_data"]


class StubSessionAuthClient:
    def get_cookies(self) -> dict[str, str] | None:
        return None


class StubRetryInvoker:
    def invoke(self, function_name: str, payload: dict[str, bool]) -> None:
        pass


@pytest.fixture(scope="module")
def client() -> RERClient:
    if not COOKIES_FILE.exists():
        pytest.skip(f"RER cookie file not found: {COOKIES_FILE}")
    cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    return RERClient(auth_cookies=cookies)


@pytest.fixture(scope="module")
def scraper() -> RERScraperService:
    return RERScraperService(
        smartsuite=StubSmartSuiteClient(),  # type: ignore[arg-type]
        session_auth=StubSessionAuthClient(),  # type: ignore[arg-type]
        retry_invoker=StubRetryInvoker(),  # type: ignore[arg-type]
        function_name="test-scraper",
    )


def test_print_refresh_data(scraper: RERScraperService, client: RERClient):
    user, organisations, stations, certificates = scraper.get_current_data(client)

    print("User:")
    print(json.dumps(user, default=asdict, indent=2))
    print("Organisations:")
    print(json.dumps(organisations, default=asdict, indent=2))
    print("Stations:")
    print(json.dumps(stations, default=asdict, indent=2))
    print("Certificates:")
    print(json.dumps(certificates, default=asdict, indent=2))
