from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from time import monotonic, sleep

import pytest
import requests
from dotenv import load_dotenv

from rer_session_auth.store import SmartSuiteCookieStore

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_live_store() -> SmartSuiteCookieStore:
    load_dotenv(REPO_ROOT / ".env")
    store = SmartSuiteCookieStore.from_env()

    missing = [
        name
        for name, value in {
            "SMARTSUITE_API_TOKEN": store.api_token,
            "SMARTSUITE_ACCOUNT_ID": store.account_id,
            "SMARTSUITE_TABLE_ID": store.table_id,
            "SMARTSUITE_RECORD_ID": store.record_id,
            "SMARTSUITE_COOKIES_FIELD": store.cookies_field,
        }.items()
        if not value
    ]
    if missing:
        pytest.skip(f"Missing SmartSuite config for live test: {', '.join(missing)}")
    return store


def _patch_raw_fields(store: SmartSuiteCookieStore, payload: dict[str, object]) -> None:
    response = store.session.patch(
        store._record_url(), json=payload, timeout=store.timeout
    )
    response.raise_for_status()


def _restore_record_fields(
    store: SmartSuiteCookieStore, original_record: dict[str, object]
) -> None:
    restore_payload: dict[str, object] = {
        store.cookies_field: original_record.get(store.cookies_field, ""),
    }
    if store.refreshed_at_field:
        restore_payload[store.refreshed_at_field] = original_record.get(
            store.refreshed_at_field, ""
        )
    _patch_raw_fields(store, restore_payload)


def _load_session_auth_api_config() -> tuple[str, str, str]:
    load_dotenv(REPO_ROOT / ".env")
    api_url = os.getenv("RER_SESSION_AUTH_API_URL")
    api_key_name = os.getenv("RER_SESSION_AUTH_API_KEY_NAME")
    api_key_value = os.getenv("RER_SESSION_AUTH_API_KEY_VALUE")
    if not api_url or not api_key_name or not api_key_value:
        pytest.skip(
            "Missing RER_SESSION_AUTH_API_URL, RER_SESSION_AUTH_API_KEY_NAME, or "
            "RER_SESSION_AUTH_API_KEY_VALUE for live session-auth test."
        )
    return api_url.rstrip("/"), api_key_name, api_key_value


def test_smartsuite_store_round_trip_live():
    store = _load_live_store()

    record_response = store.session.get(store._record_url(), timeout=store.timeout)
    record_response.raise_for_status()
    original_record = record_response.json()

    original_cookies_present = store.cookies_field in original_record
    original_cookies_value = original_record.get(store.cookies_field)
    original_refreshed_present = bool(
        store.refreshed_at_field and store.refreshed_at_field in original_record
    )
    original_refreshed_value = (
        original_record.get(store.refreshed_at_field)
        if store.refreshed_at_field
        else None
    )

    probe_cookies = {
        "opencode_probe": uuid.uuid4().hex,
        "opencode_probe_session": "smart-suite-round-trip",
    }

    try:
        store.save_cookies(probe_cookies)
        loaded_cookies = store.load_auth_params()
        assert loaded_cookies == probe_cookies

        updated_record_response = store.session.get(
            store._record_url(), timeout=store.timeout
        )
        updated_record_response.raise_for_status()
        updated_record = updated_record_response.json()
        assert json.loads(updated_record[store.cookies_field]) == probe_cookies
    finally:
        restore_payload: dict[str, object] = {
            store.cookies_field: (
                original_cookies_value if original_cookies_present else ""
            ),
        }
        if store.refreshed_at_field:
            restore_payload[store.refreshed_at_field] = (
                original_refreshed_value if original_refreshed_present else ""
            )
        _patch_raw_fields(store, restore_payload)


def test_session_auth_starts_refresh_and_caches_cookies_live():
    store = _load_live_store()
    api_url, api_key_name, api_key_value = _load_session_auth_api_config()

    record_response = store.session.get(store._record_url(), timeout=store.timeout)
    record_response.raise_for_status()
    original_record = record_response.json()

    try:
        _patch_raw_fields(store, {store.cookies_field: ""})
        assert store.load_auth_params() is None

        response = requests.get(
            api_url,
            headers={"x-api-key": api_key_value},
            timeout=30,
        )
        if response.status_code == 403:
            pytest.fail(
                "Session-auth API Gateway rejected the configured credentials for "
                f"{api_url}/user using API key {api_key_name!r}: {response.text}"
            )
        assert response.status_code == 202
        assert response.json() == {"status": "refreshing"}

        deadline = monotonic() + 300
        refreshed_cookies = None
        while monotonic() < deadline:
            refreshed_cookies = store.load_auth_params()
            if refreshed_cookies:
                break
            sleep(60)
        assert refreshed_cookies
        assert all(
            name is not None and not name.startswith("ai_")
            for name in refreshed_cookies
        )
    finally:
        _restore_record_fields(store, original_record)
