from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol
import boto3  # type: ignore[import-not-found] - boto3 is included in lambda env and not needed locally

from rer_session_auth.auth import (
    RERAuthConfig,
    are_cookies_valid,
    browser_authenticate_rer,
    _sanitize_cookies,
)
from rer_session_auth.store import SmartSuiteCookieStore

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


class RefreshInvoker(Protocol):
    def invoke(self, payload: dict[str, Any]) -> None: ...


class Boto3RefreshInvoker:
    def __init__(self, function_name: str):

        self.client = boto3.client("lambda")
        self.function_name = function_name

    def invoke(self, payload: dict[str, Any]) -> None:
        self.client.invoke(
            FunctionName=self.function_name,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )


class SessionCookieService:
    def __init__(
        self,
        store: SmartSuiteCookieStore,
        refresh_invoker: RefreshInvoker,
        auth_config: RERAuthConfig,
        function_name: str,
    ):
        self.store = store
        self.refresh_invoker = refresh_invoker
        self.auth_config = auth_config
        self.function_name = function_name

    def get_cookies(self) -> dict[str, Any]:
        cached_cookies = _sanitize_cookies(self.store.load_auth_params()[0] or {})
        return cached_cookies

    def refresh_cookies(self) -> None:
        log.info("Refreshing RER session cookies")
        refreshed_cookies = _sanitize_cookies(
            browser_authenticate_rer(self.auth_config)
        )
        log.info(
            "RER authentication completed; saving %s cookies", len(refreshed_cookies)
        )
        self.store.save_cookies(refreshed_cookies)
        log.info("Saved refreshed RER session cookies")


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def build_cookie_service(context) -> SessionCookieService:
    function_name = context.invoked_function_arn

    store = SmartSuiteCookieStore.from_env()
    auth_params = store.load_auth_params()
    email = auth_params[1]
    password = auth_params[2]

    return SessionCookieService(
        store=store,
        refresh_invoker=Boto3RefreshInvoker(function_name),
        auth_config=RERAuthConfig.from_env(email, password),
        function_name=function_name,
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    service = build_cookie_service(context)
    if event.get("refresh_cookies") is True:
        # This code path is only reached when cookies are invalid and another lambda invocation has requested a refresh
        service.refresh_cookies()
        return None
    # Else get cookies and check validity
    cookies = service.get_cookies()
    if are_cookies_valid(cookies):
        log.info("Returning cached RER session cookies")
        return _response(200, {"cookies": cookies})
    else:
        log.info(
            "Cached RER cookies are missing or invalid. Scheduling cookie refresh."
        )
        service.refresh_invoker.invoke(payload={"refresh_cookies": True})
        return _response(
            202,
            {
                "message": "Stored RER session has expired and needs to be refreshed. Please try again in around a minute."
            },
        )


# region testing

if __name__ == "__main__":

    context = type(
        "Context", (), {"invoked_function_arn": "local-RERScraperFunction"}
    )()
    # test the refresh_cookies functionality (usually invoked asynchronously when cached cookies are invalid))
    result = handler({"refresh_cookies": True}, context)
    print(result)

# endregion
