from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Protocol

import requests


class CookieStore(Protocol):
    def load_auth_params(
        self,
    ) -> tuple[dict[str, str] | None, str | None, str | None]: ...

    def save_cookies(self, cookies: dict[str, str]) -> None: ...


class SmartSuiteCookieStore:
    def __init__(
        self,
        api_url: str | None,
        api_token: str | None,
        account_id: str | None,
        table_id: str | None,
        record_id: str | None,
        cookies_field: str,
        email_field: str | None,
        password_field: str | None,
        refreshed_at_field: str | None,
        timeout: int = 30,
    ):
        self.api_url = (api_url or "https://app.smartsuite.com/api/v1").rstrip("/")
        self.api_token = api_token
        self.account_id = account_id
        self.table_id = table_id
        self.record_id = record_id
        self.cookies_field = cookies_field
        self.email_field = email_field
        self.password_field = password_field
        self.refreshed_at_field = refreshed_at_field
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {api_token}" if api_token else "",
                "ACCOUNT-ID": account_id or "",
                "Content-Type": "application/json",
            }
        )

    @classmethod
    def from_env(cls) -> "SmartSuiteCookieStore":
        return cls(
            api_url=os.getenv("SMARTSUITE_API_URL"),
            api_token=os.getenv("SMARTSUITE_API_TOKEN"),
            account_id=os.getenv("SMARTSUITE_ACCOUNT_ID"),
            table_id=os.getenv("SMARTSUITE_TABLE_ID"),
            record_id=os.getenv("SMARTSUITE_RECORD_ID"),
            cookies_field=os.getenv("SMARTSUITE_COOKIES_FIELD", "session_cookies"),
            email_field="sb966ee382",
            password_field="sb4e5173b6",
            refreshed_at_field=os.getenv("SMARTSUITE_REFRESHED_AT_FIELD"),
            timeout=int(os.getenv("SMARTSUITE_TIMEOUT_SECONDS", "30")),
        )

    def load_auth_params(self) -> tuple[dict[str, str] | None, str | None, str | None]:
        response = self.session.get(self._record_url(), timeout=self.timeout)
        response.raise_for_status()
        record = response.json()

        raw_value = record.get(self.cookies_field)
        email = record.get(self.email_field)
        password = record.get(self.password_field)
        if raw_value is None:
            return None, email, password

        cookies = self._coerce_cookies(raw_value)
        return cookies or None, email, password

    def save_cookies(self, cookies: dict[str, str]) -> None:
        payload: dict[str, str] = {
            self.cookies_field: json.dumps(cookies, sort_keys=True),
        }
        if self.refreshed_at_field:
            payload[self.refreshed_at_field] = datetime.now(UTC).isoformat()

        response = self.session.patch(
            self._record_url(), json=payload, timeout=self.timeout
        )
        response.raise_for_status()

    def _record_url(self) -> str:
        self._validate_configuration()
        assert self.table_id is not None
        assert self.record_id is not None
        return f"{self.api_url}/applications/{self.table_id}/records/{self.record_id}/"

    def _validate_configuration(self) -> None:
        missing = []
        if not self.api_token:
            missing.append("SMARTSUITE_API_TOKEN")
        if not self.account_id:
            missing.append("SMARTSUITE_ACCOUNT_ID")
        if not self.table_id:
            missing.append("SMARTSUITE_TABLE_ID")
        if not self.record_id:
            missing.append("SMARTSUITE_RECORD_ID")
        if not self.cookies_field:
            missing.append("SMARTSUITE_COOKIES_FIELD")
        if missing:
            raise RuntimeError(
                f"Missing SmartSuite configuration: {', '.join(missing)}"
            )

    def _coerce_cookies(self, raw_value: object) -> dict[str, str]:
        if isinstance(raw_value, str):
            if not raw_value.strip():
                return {}
            parsed = json.loads(raw_value)
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"Expected JSON object in SmartSuite field {self.cookies_field}."
                )
            return self._stringify_cookie_values(parsed)

        if isinstance(raw_value, dict):
            return self._stringify_cookie_values(raw_value)

        raise ValueError(
            f"Unsupported cookie payload type {type(raw_value).__name__!r} in SmartSuite field {self.cookies_field}."
        )

    @staticmethod
    def _stringify_cookie_values(cookies: dict[object, object]) -> dict[str, str]:
        return {
            str(name): str(value)
            for name, value in cookies.items()
            if value is not None
        }


def build_cookie_store() -> CookieStore:
    return SmartSuiteCookieStore.from_env()
