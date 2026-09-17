from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

from rer_session_auth.auth import (
    RERAuthConfig,
    are_cookies_valid,
    browser_authenticate_rer,
    sanitize_cookies,
)
from rer_session_auth.store import CookieStore, build_cookie_store

log = logging.getLogger(__name__)


class RefreshInvoker(Protocol):
    def invoke(self, function_name: str, payload: dict[str, Any]) -> None: ...


class Boto3RefreshInvoker:
    def __init__(self):
        import boto3  # type: ignore[import-not-found]

        self.client = boto3.client("lambda")

    def invoke(self, function_name: str, payload: dict[str, Any]) -> None:
        self.client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )


class SessionCookieService:
    def __init__(
        self,
        store: CookieStore,
        refresh_invoker: RefreshInvoker,
        auth_config: RERAuthConfig,
        function_name: str,
    ):
        self.store = store
        self.refresh_invoker = refresh_invoker
        self.auth_config = auth_config
        self.function_name = function_name

    def get_cookies(self) -> dict[str, Any]:
        cached_cookies = sanitize_cookies(self.store.load_auth_params()[0] or {})
        if cached_cookies and are_cookies_valid(cached_cookies):
            log.info("Returning cached RER session cookies")
            return _response(200, {"cookies": cached_cookies})

        log.info("Cached RER cookies are missing or invalid. Starting refresh.")
        self.refresh_invoker.invoke(self.function_name, {"refresh_cookies": True})
        return _response(202, {"status": "refreshing"})

    def refresh_cookies(self) -> None:
        log.info("Refreshing RER session cookies")
        refreshed_cookies = sanitize_cookies(browser_authenticate_rer(self.auth_config))
        self.store.save_cookies(refreshed_cookies)
        log.info("Saved refreshed RER session cookies")


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def build_cookie_service() -> SessionCookieService:
    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        raise RuntimeError(
            "AWS_LAMBDA_FUNCTION_NAME is required to start a cookie refresh."
        )

    store = build_cookie_store()
    email = store.load_auth_params()[1]
    password = store.load_auth_params()[2]

    return SessionCookieService(
        store=store,
        refresh_invoker=Boto3RefreshInvoker(),
        auth_config=RERAuthConfig.from_env(email, password),
        function_name=function_name,
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    del context
    service = build_cookie_service()
    if event.get("refresh_cookies") is True:
        service.refresh_cookies()
        return None
    return service.get_cookies()
