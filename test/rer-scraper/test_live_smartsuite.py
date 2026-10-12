from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
import pytz
from dotenv import load_dotenv

from rer_scraper.smartsuite import RERSmartSuiteClient


def test_live_get_operations_filter():
    """Exercise the real read-only SmartSuite query used by the scraper."""
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    if os.getenv("RUN_LIVE_SMARTSUITE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_SMARTSUITE_TESTS=1 to query SmartSuite.")

    account_id = os.getenv("SMARTSUITE_ACCOUNT_ID")
    api_token = os.getenv("SMARTSUITE_API_TOKEN")
    if not account_id or not api_token:
        pytest.skip("SMARTSUITE_ACCOUNT_ID and SMARTSUITE_API_TOKEN must be set.")

    client = RERSmartSuiteClient(account_id=account_id, api_token=api_token)
    operations = client.get_operations(datetime.now(pytz.timezone("Europe/London")))

    assert isinstance(operations, list)
    assert set(operations) <= {"refresh_data", "transfer_certificates"}
    print(
        f"SmartSuite accepted get_operations filter; pending operations: {operations}"
    )
