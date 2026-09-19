from __future__ import annotations

import json
from typing import Any

from rer_session_auth.auth import RERAuthConfig
from rer_session_auth.handler import SessionCookieService


class StubStore:
    def __init__(self, cookies: dict[str, str] | None):
        self.cookies = cookies
        self.saved_cookies: dict[str, str] | None = None

    def load_auth_params(
        self,
    ) -> tuple[dict[str, str] | None, str | None, str | None]:
        return self.cookies, None, None

    def load_cookies(self) -> dict[str, str] | None:
        return self.cookies

    def save_cookies(self, cookies: dict[str, str]) -> None:
        self.saved_cookies = cookies


class StubRefreshInvoker:
    def __init__(self):
        self.function_name: str | None = None
        self.payload: dict[str, Any] | None = None

    def invoke(self, function_name: str, payload: dict[str, Any]) -> None:
        self.function_name = function_name
        self.payload = payload


def make_service(store: StubStore, invoker: StubRefreshInvoker) -> SessionCookieService:
    return SessionCookieService(
        store=store,
        refresh_invoker=invoker,
        auth_config=RERAuthConfig(
            email="user@example.com",
            password="secret",
            gmail_token_json="{}",
            gmail_token_file=None,
        ),
        function_name="session-auth-function",
    )


def test_returns_valid_cached_cookies(monkeypatch):
    store = StubStore({"session": "cached", "ai_session": "ignored"})
    invoker = StubRefreshInvoker()
    service = make_service(store, invoker)

    monkeypatch.setattr(
        "rer_session_auth.handler.are_cookies_valid",
        lambda cookies: cookies == {"session": "cached"},
    )

    response = service.get_cookies()

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"cookies": {"session": "cached"}}
    assert invoker.function_name is None
    assert store.saved_cookies is None


def test_starts_background_refresh_for_invalid_cookies(monkeypatch):
    store = StubStore({"session": "stale"})
    invoker = StubRefreshInvoker()
    service = make_service(store, invoker)

    monkeypatch.setattr(
        "rer_session_auth.handler.are_cookies_valid", lambda cookies: False
    )
    response = service.get_cookies()

    assert response["statusCode"] == 202
    assert json.loads(response["body"]) == {"status": "refreshing"}
    assert invoker.function_name == "session-auth-function"
    assert invoker.payload == {"refresh_cookies": True}
    assert store.saved_cookies is None


def test_refreshes_and_saves_cookies(monkeypatch):
    store = StubStore(None)
    service = make_service(store, StubRefreshInvoker())
    monkeypatch.setattr(
        "rer_session_auth.handler.browser_authenticate_rer",
        lambda config: {"session": "fresh", "ai_debug": "drop-me"},
    )

    service.refresh_cookies()

    assert store.saved_cookies == {"session": "fresh"}
