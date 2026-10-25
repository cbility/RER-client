from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

from rer_session_auth.auth import (
    RERAuthConfig,
    are_cookies_valid,
    browser_authenticate_rer,
)
from rer_session_auth.store import SmartSuiteUserDataStore

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


class RefreshInvoker(Protocol):
    def invoke(self, payload: dict[str, Any]) -> None: ...


class Boto3RefreshInvoker:
    def __init__(self, function_name: str):
        import boto3  # type: ignore[import-not-found] - boto3 is included in lambda env and not needed locally

        self.client = boto3.client("lambda")
        self.function_name = function_name

    def invoke(self, payload: dict[str, Any]) -> None:
        self.client.invoke(
            FunctionName=self.function_name,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )


def refresh_cookies(store: SmartSuiteUserDataStore, auth_config: RERAuthConfig) -> None:
    log.info("Refreshing RER session cookies")
    refreshed_cookies = browser_authenticate_rer(auth_config)
    log.info("RER authentication completed; saving %s cookies", len(refreshed_cookies))
    store.save_cookies(refreshed_cookies)
    log.info("Saved refreshed RER session cookies")


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    # get user data from smartsuite
    store = SmartSuiteUserDataStore.from_env()
    cookies, email, password = store.load_auth_params()

    if event.get("refresh_cookies") is True:
        # This code path is only reached when cookies are invalid and another lambda invocation has requested a refresh
        auth_config = RERAuthConfig.from_env(email, password)
        refresh_cookies(store, auth_config)
        return None

    # Else get cookies and check validity
    auth_config = RERAuthConfig.from_env(email, password)
    if are_cookies_valid(cookies):
        log.info("Returning cached RER session cookies")
        return _response(200, {"cookies": cookies})
    else:
        log.info(
            "Cached RER cookies are missing or invalid. Scheduling cookie refresh."
        )
        # asynchronously invoke the refresh of cookies
        Boto3RefreshInvoker(context.invoked_function_arn).invoke(
            payload={"refresh_cookies": True}
        )
        return _response(
            202,
            {
                "message": "Stored RER session has expired and needs to be refreshed. Please try again in around a minute."
            },
        )


# region testing

if __name__ == "__main__":

    import os

    os.environ["PLAYWRIGHT_HEADLESS"] = "0"
    os.environ["RER_LOCAL_TEST"] = "1"
    os.environ["LOG_LEVEL"] = "DEBUG"

    context = type(
        "Context", (), {"invoked_function_arn": "local-RERScraperFunction"}
    )()
    # test the refresh_cookies functionality (usually invoked asynchronously when cached cookies are invalid))
    result = handler({"refresh_cookies": True}, context)
    print(result)

# endregion
