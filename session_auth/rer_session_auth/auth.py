from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import NotRequired, TypedDict

import requests

log = logging.getLogger(__name__)

RER_BASE_URL = "https://rer.ofgem.gov.uk/"
RER_SIGN_IN_URL = f"{RER_BASE_URL}Account/SignIn"
RER_USER_URL = f"{RER_BASE_URL}User"
RER_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


class MissingConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RERAuthConfig:
    email: str | None
    password: str | None
    gmail_token_json: str | None
    gmail_token_file: str | None
    headless: bool = True
    max_retries: int = 5
    wait_between_retries: int = 10

    @classmethod
    def from_env(cls, email, password) -> "RERAuthConfig":
        return cls(
            email=email,
            password=password,
            gmail_token_json=os.getenv("GMAIL_TOKEN_JSON"),
            gmail_token_file=os.getenv("GMAIL_TOKEN_FILE"),
            headless=_env_bool("PLAYWRIGHT_HEADLESS", True),
            max_retries=int(os.getenv("RER_MFA_MAX_RETRIES", "5")),
            wait_between_retries=int(os.getenv("RER_MFA_WAIT_SECONDS", "10")),
        )


class GmailMessageBody(TypedDict):
    data: str
    size: int
    attachmentId: NotRequired[str]


class GmailMessagePart(TypedDict, total=False):
    partId: str
    mimeType: str
    filename: str
    body: GmailMessageBody
    parts: list["GmailMessagePart"]


class GmailMessagePayload(TypedDict, total=False):
    partId: str
    mimeType: str
    filename: str
    body: GmailMessageBody
    parts: list[GmailMessagePart]


class GmailMessage(TypedDict):
    id: str
    threadId: str
    payload: NotRequired[GmailMessagePayload]
    internalDate: NotRequired[str]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def sanitize_cookies(cookies: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in cookies.items() if not key.startswith("ai_")}


def build_cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def build_session(cookies: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(RER_DEFAULT_HEADERS)
    if cookies:
        session.cookies.update(cookies)
    return session


def are_cookies_valid(cookies: dict[str, str], timeout: int = 30) -> bool:
    if not cookies:
        return False

    try:
        response = build_session(cookies).get(
            RER_USER_URL, timeout=timeout, allow_redirects=False
        )
    except requests.RequestException:
        log.exception("Failed to validate cached RER cookies")
        return False

    if response.status_code != 200:
        return False

    location = response.headers.get("Location", "")
    if "Account/SignIn" in location or "b2c_1a_rer_signin" in location:
        return False

    sign_in_markers = (
        'id="signInName"',
        'name="signInName"',
        "b2c_1a_rer_signin",
        "/Account/SignIn",
    )
    return not any(marker in response.text for marker in sign_in_markers)


def get_no_token_error_message(token_file_path: Path) -> str:
    return f"""
{'=' * 80}
ERROR: {token_file_path} not found
{'=' * 80}
Gmail API requires OAuth2 authentication. Follow these steps:
1. Create OAuth2 desktop app credentials in Google Cloud Console.
2. Enable the Gmail API.
3. Add your Gmail address as a test user if the OAuth app is in testing.
4. Run an OAuth flow that writes {token_file_path}.

Example:
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(
        "gmail_credentials.json",
        ["https://mail.google.com/"],
    )
    creds = flow.run_local_server(port=0)
    with open(r"{token_file_path}", "w") as f:
        f.write(creds.to_json())
{'=' * 80}
"""


def _load_gmail_credentials(token_json: str | None, token_file: str | None):
    from google.auth.transport.requests import Request  # type: ignore[import-untyped]
    from google.oauth2.credentials import Credentials  # type: ignore[import-untyped]

    if token_json:
        info = json.loads(token_json)
        credentials = Credentials.from_authorized_user_info(
            info, ["https://mail.google.com/"]
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        return credentials

    if not token_file:
        raise MissingConfigurationError(
            "Set GMAIL_TOKEN_JSON or GMAIL_TOKEN_FILE so the auth Lambda can retrieve MFA emails."
        )

    token_path = Path(token_file)
    if not token_path.exists():
        raise FileNotFoundError(get_no_token_error_message(token_path))

    credentials = Credentials.from_authorized_user_file(
        token_path, ["https://mail.google.com/"]
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def get_gmail_messages(
    since_date: dt.date,
    max_messages: int,
    token_json: str | None,
    token_file: str | None,
) -> list[GmailMessage]:
    from googleapiclient.discovery import build  # type: ignore[import-untyped]

    credentials = _load_gmail_credentials(token_json=token_json, token_file=token_file)
    service = build("gmail", "v1", credentials=credentials)
    query = f'after:{since_date.strftime("%Y/%m/%d")}'
    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_messages)
        .execute()
    )
    message_refs = results.get("messages", [])

    messages: list[GmailMessage] = []
    for message_ref in message_refs:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_ref["id"], format="full")
            .execute()
        )
        messages.append(message)
    return messages


def decode_message_body(payload: GmailMessagePayload | GmailMessagePart | None) -> str:
    if not payload:
        return ""

    body = payload.get("body", {})
    data = body.get("data")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8")

    return "\n".join(decode_message_body(part) for part in payload.get("parts", []))


def retrieve_mfa_code(
    button_clicked_after: dt.datetime,
    token_json: str | None,
    token_file: str | None,
    max_retries: int,
    wait_between_retries: int,
) -> str:
    for retry_number in range(max_retries):
        log.info(
            "Attempting to retrieve MFA code (%s/%s)", retry_number + 1, max_retries
        )
        messages_today = get_gmail_messages(
            since_date=button_clicked_after.date(),
            max_messages=10,
            token_json=token_json,
            token_file=token_file,
        )
        messages_after_click = [
            message
            for message in messages_today
            if dt.datetime.fromtimestamp(int(message.get("internalDate", 0)) / 1000)
            > button_clicked_after
        ]

        for message in messages_after_click:
            body_text = decode_message_body(message.get("payload"))
            if "RER-External-prd authentication" not in body_text:
                continue

            match = re.search(r"verification code (\d{6})", body_text)
            if match:
                return match.group(1)

        log.warning(
            "MFA email not found. Retrying in %s seconds.", wait_between_retries
        )
        sleep(wait_between_retries)

    raise TimeoutError(f"Failed to retrieve MFA code after {max_retries} attempts.")


def browser_authenticate_rer(config: RERAuthConfig) -> dict[str, str]:
    from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]

    if not config.email:
        raise MissingConfigurationError("Set email in the login record on SmartSuite.")
    if not config.password:
        raise MissingConfigurationError(
            "Set password in the login record on SmartSuite."
        )

    log.info("Authenticating with RER portal as %s", config.email)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=config.headless,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--no-zygote",
            ],
        )
        page = browser.new_page()
        try:
            page.goto(RER_SIGN_IN_URL)
            page.wait_for_url("**/b2c_1a_rer_signin/**")

            page.fill("#signInName", config.email)
            page.fill("#password", config.password)
            page.click("button:has-text('Sign in')")
            page.wait_for_load_state("networkidle")

            login_error_message = page.query_selector(
                "#localAccountForm > div.error.pageLevel > p"
            )
            if login_error_message:
                raise ValueError(
                    f"Authentication failed: {login_error_message.inner_text()}"
                )

            button_clicked_after = dt.datetime.now()
            page.click("#sendCode")
            page.wait_for_load_state("networkidle")

            sleep(5)
            mfa_code = retrieve_mfa_code(
                button_clicked_after=button_clicked_after,
                token_json=config.gmail_token_json,
                token_file=config.gmail_token_file,
                max_retries=config.max_retries,
                wait_between_retries=config.wait_between_retries,
            )

            page.fill("#verificationCode", mfa_code)
            page.click("#verifyCode")
            page.wait_for_load_state("networkidle")

            error_message = page.query_selector("div.error:nth-child(2)")
            if error_message:
                error_text = error_message.inner_text().strip()
                if error_text:
                    raise ValueError(f"MFA verification failed: {error_text}")

            page.wait_for_url("https://rer.ofgem.gov.uk/**", timeout=300000)
            cookies = page.context.cookies()
            return sanitize_cookies(
                {cookie.get("name", ""): cookie.get("value", "") for cookie in cookies}
            )
        finally:
            browser.close()
