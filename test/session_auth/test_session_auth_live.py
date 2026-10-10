"""Live test script that invokes the session auth lambda handler as-is.

Usage:
    uv run python test/session_auth/test_session_auth_live.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Add session_auth to path so imports work
ROOT_DIR = Path(__file__).parent.parent.parent
SESSION_AUTH_DIR = ROOT_DIR / "session_auth"
sys.path.insert(0, str(SESSION_AUTH_DIR))

os.environ["LOG_LEVEL"] = os.getenv("LOG_LEVEL", "INFO")
os.environ["RER_LOCAL_TEST"] = "1"

from rer_session_auth.handler import SessionCookieService
from rer_session_auth.store import build_cookie_store
from rer_session_auth.auth import RERAuthConfig


class LocalRefreshInvoker:
    """Local refresh invoker that calls refresh_cookies directly (no boto3 needed)."""

    def __init__(self, service: SessionCookieService):
        self.service = service
        self.function_name = "local-test"

    def invoke(self, function_name: str, payload: dict[str, Any]) -> None:
        """Call refresh_cookies directly instead of Lambda invoke."""
        if payload.get("refresh_cookies"):
            print("\n→ Invoking refresh_cookies()...")
            self.service.refresh_cookies()


def main():
    """Invoke the session auth service directly (mimics Lambda flow)."""

    # Build service with local invoker (no boto3 required)
    store = build_cookie_store()
    email, password = store.load_auth_params()[1:3]

    print(f"Testing with email: {email}")
    print()

    auth_config = RERAuthConfig(
        email=email,
        password=password,
        gmail_token_json=os.getenv("GMAIL_TOKEN_JSON"),
        gmail_token_file=os.getenv("GMAIL_TOKEN_FILE"),
        headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
    )

    service = SessionCookieService(
        store=store,
        refresh_invoker=None,  # Will set below # type: ignore
        auth_config=auth_config,
        function_name="local-test",
    )
    service.refresh_invoker = LocalRefreshInvoker(service)

    print("→ Getting RER session cookies...")
    print("-" * 80)

    response = service.get_cookies()

    status_code = response.get("statusCode")
    body = json.loads(response.get("body", "{}"))

    print(f"\n← Response:")
    print(f"  Status: {status_code}")
    print(f"  Body: {json.dumps(body, indent=4)}")


if __name__ == "__main__":
    sys.exit(main())
