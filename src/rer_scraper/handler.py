from __future__ import annotations

from dataclasses import asdict
import json
import os
from typing import Any

from rer_scraper.service import (
    RERScraperService,
    RetryInvoker,
    SessionAuthClient,
)
from rer_scraper.smartsuite import RERSmartSuiteClient


class SessionRefreshPending(RuntimeError):
    pass


class Boto3RetryInvoker:
    def __init__(self):
        import boto3  # type: ignore[import-not-found]

        self.client = boto3.client("lambda")

    def invoke(self, function_name: str, payload: dict[str, Any]) -> None:
        self.client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )


def build_service(dry_run: bool = False) -> RERScraperService:
    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    auth_api_url = os.getenv("RER_SESSION_AUTH_API_URL")
    auth_api_key = os.getenv("RER_SESSION_AUTH_API_KEY_VALUE")
    smartsuite_account_id = os.getenv("SMARTSUITE_ACCOUNT_ID")
    smartsuite_api_key = os.getenv("SMARTSUITE_API_TOKEN")
    ss_login_record_id = "6a7f301f54fd4d6f819c1e5f"

    if not function_name:
        raise RuntimeError(
            "AWS_LAMBDA_FUNCTION_NAME is required to schedule a scraper retry."
        )
    if not auth_api_url or not auth_api_key:
        raise RuntimeError(
            "Set RER_SESSION_AUTH_API_URL and RER_SESSION_AUTH_API_KEY_VALUE environment variables."
        )
    if not smartsuite_account_id or not smartsuite_api_key:
        raise RuntimeError(
            "Set SMARTSUITE_ACCOUNT_ID and SMARTSUITE_API_TOKEN environment variables."
        )

    return RERScraperService(
        smartsuite=RERSmartSuiteClient(
            account_id=smartsuite_account_id, api_token=smartsuite_api_key
        ),
        session_auth=SessionAuthClient(auth_api_url, auth_api_key),
        retry_invoker=Boto3RetryInvoker(),
        function_name=function_name,
        ss_login_record_id=ss_login_record_id,
        dry_run=dry_run,
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    del context
    service = build_service()
    organisation_reference = (event.get("queryStringParameters") or {}).get(
        "organisation_reference"
    )
    if event.get("retry_scrape") is True:
        status_code, _ = service.run(
            schedule_retry=False, organisation_reference=organisation_reference
        )
        if status_code == 202:
            raise SessionRefreshPending("RER session refresh is still in progress.")
        return None

    status_code, result = service.run(organisation_reference=organisation_reference)
    if status_code == 204:
        return {"statusCode": 204}
    if status_code == 202:
        return {
            "statusCode": 202,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"status": "waiting_for_session_refresh"}),
        }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": RERScraperService.parse_scraper_result(result),
    }
