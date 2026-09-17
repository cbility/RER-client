from __future__ import annotations

import json

import pytest

from rer_session_auth.store import SmartSuiteCookieStore


class StubResponse:
    def __init__(self, payload, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class StubSession:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.get_calls: list[tuple[str, int]] = []
        self.patch_calls: list[tuple[str, dict[str, str], int]] = []
        self.get_response = StubResponse({})
        self.patch_response = StubResponse({})

    def get(self, url: str, timeout: int):
        self.get_calls.append((url, timeout))
        return self.get_response

    def patch(self, url: str, json: dict[str, str], timeout: int):
        self.patch_calls.append((url, json, timeout))
        return self.patch_response


def make_store(
    *, cookies_field: str = "session_cookies", refreshed_at_field: str | None = None
) -> SmartSuiteCookieStore:
    store = SmartSuiteCookieStore(
        api_url="https://app.smartsuite.com/api/v1",
        api_token="token-123",
        email_field="sb966ee382",
        password_field="sb4e5173b6",
        account_id="workspace-456",
        table_id="table-789",
        record_id="record-101",
        cookies_field=cookies_field,
        refreshed_at_field=refreshed_at_field,
        timeout=12,
    )
    store.session = StubSession()  # type: ignore[assignment]
    return store


def test_load_cookies_reads_json_string_field():
    store = make_store()
    store.session.get_response = StubResponse({"session_cookies": '{"foo": "bar"}'})  # type: ignore[attr-defined]

    cookies = store.load_auth_params()

    assert cookies == {"foo": "bar"}
    assert store.session.get_calls == [  # type: ignore[attr-defined]
        (
            "https://app.smartsuite.com/api/v1/applications/table-789/records/record-101/",
            12,
        )
    ]


def test_load_cookies_accepts_object_field():
    store = make_store()
    store.session.get_response = StubResponse({"session_cookies": {"foo": "bar", "baz": 1}})  # type: ignore[attr-defined]

    assert store.load_auth_params() == {"foo": "bar", "baz": "1"}


def test_load_cookies_returns_none_when_field_missing():
    store = make_store()
    store.session.get_response = StubResponse({"other": "value"})  # type: ignore[attr-defined]

    assert store.load_auth_params() is None


def test_save_cookies_patches_record_with_json_string():
    store = make_store(refreshed_at_field="refreshed_at")

    store.save_cookies({"foo": "bar"})

    assert len(store.session.patch_calls) == 1  # type: ignore[attr-defined]
    url, payload, timeout = store.session.patch_calls[0]  # type: ignore[attr-defined]
    assert (
        url
        == "https://app.smartsuite.com/api/v1/applications/table-789/records/record-101/"
    )
    assert json.loads(payload["session_cookies"]) == {"foo": "bar"}
    assert "refreshed_at" in payload
    assert timeout == 12


def test_validate_configuration_requires_account_id():
    store = SmartSuiteCookieStore(
        api_url="https://app.smartsuite.com/api/v1",
        api_token="token-123",
        account_id=None,
        table_id="table-789",
        email_field="sb966ee382",
        password_field="sb4e5173b6",
        record_id="record-101",
        cookies_field="session_cookies",
        refreshed_at_field=None,
    )

    with pytest.raises(RuntimeError, match="SMARTSUITE_ACCOUNT_ID"):
        store.load_auth_params()


def test_load_cookies_rejects_invalid_payload_type():
    store = make_store()
    store.session.get_response = StubResponse({"session_cookies": ["bad"]})  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="Unsupported cookie payload type"):
        store.load_auth_params()
