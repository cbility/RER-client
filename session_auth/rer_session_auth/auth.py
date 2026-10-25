# region imports

import datetime as dt
import json
import logging
import os
import re
from google import genai
from dataclasses import dataclass
from time import sleep
from typing import TypedDict

import requests

# endregion imports

# region config

log = logging.getLogger(__name__)

RER_BASE_URL = "https://rer.ofgem.gov.uk/"
RER_SIGN_IN_URL = f"{RER_BASE_URL}Account/SignIn"
RER_USER_URL = f"{RER_BASE_URL}User"
MAKE_EMAILER_URL = "https://hook.eu2.make.com/xawri30n5fdswaet4672pl4vbs7imx8c"
MAKE_GET_MFA_EMAILS_URL = "https://hook.eu2.make.com/lcn1lkdpu74lux5xxrgigxgc5i2dqxoc"
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

# endregion config

# region classes


class MissingConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RERAuthConfig:
    email: str | None
    password: str | None
    headless: bool = True
    max_retries: int = 2
    wait_between_retries: int = 15

    @classmethod
    def from_env(cls, email, password) -> "RERAuthConfig":
        return cls(
            email=email,
            password=password,
            headless=_env_bool("PLAYWRIGHT_HEADLESS", True),
            max_retries=int(os.getenv("RER_MFA_MAX_RETRIES", "2")),
            wait_between_retries=int(os.getenv("RER_MFA_WAIT_SECONDS", "15")),
        )


class GmailMessage(TypedDict):
    date: str  # ISO string
    html: str  # message content


# endregion classes

# region helpers


def _solve_captcha(image_data_url: str) -> str:

    client = genai.Client()
    log.info("Sending CAPTCHA to Gemini 3.8 Flash for solving")

    # remove data: prefix from image url
    image_data = (
        image_data_url.split(",", 1)[1] if "," in image_data_url else image_data_url
    )

    interaction = client.interactions.create(
        model="gemini-3.8-flash",
        input=[
            {
                "type": "text",
                "text": "What text does this image show? Return ONLY the exact text, no spaces, no explanation.",
            },
            {"type": "image", "data": image_data, "mime_type": "image/jpeg"},
        ],
    )
    result = interaction.output_text

    if not result:
        log.warning("No text found in response, dumping full response for debugging")
        log.info("Full response: %s", interaction)
        raise RuntimeError("Failed to extract text from response")

    log.info("CAPTCHA solution returned: %s", result.strip())
    return result.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _sanitize_cookies(cookies: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in cookies.items() if not key.startswith("ai_")}


def _send_password_failure_notification(user_email: str, error_message: str) -> None:
    """Send email notification when password authentication fails.

    Args:
        user_email: The email address that failed to authenticate
        error_message: The authentication error message from RER
    """
    # Determine recipient: use user email in production, test email for local dev
    # Check if running in local test mode (RER_LOCAL_TEST env var)
    is_local_test = os.getenv("RER_LOCAL_TEST") is not None
    recipient = "ap.johnston@outlook.com" if is_local_test else user_email

    subject = "RER Scraper Authentication Failed - Password Correction Required"

    html_body = f"""
    <html>
    <body>
        <h2>RER Scraper Authentication Failure</h2>
        <p><strong>Automatic login failed for:</strong> {user_email}</p>
        <p>The RER returned the following message: <strong>{error_message}</strong></p>
        <p>This probably means that the password saved on SmartSuite for the RER account is incorrect.<br>You should correct the password ASAP, as the scraper will continue to fail until it is updated.</p>
        <hr>
        <p><em>This is an automated notification from the RER Session Auth Lambda.</em></p>
    </body>
    </html>
    """

    payload = {
        "to": recipient,
        "cc": "",
        "bcc": "",
        "from": "RER Scraper Monitor <noreply@rer-scraper.monitor>",
        "subject": subject,
        "html": html_body,
    }

    try:
        log.info("Sending password failure notification to %s", recipient)
        response = requests.post(
            MAKE_EMAILER_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        log.info("Password failure notification sent successfully")
    except requests.RequestException as e:
        log.error("Failed to send password failure notification: %s", e)
        # Don't re-raise - we still want to raise the original auth error


def _send_mfa_retrieval_failure_notification(
    user_email: str, error_message: str
) -> None:
    """Send email notification when MFA retrieval fails.

    Args:
        user_email: The email address that failed to authenticate
        error_message: The authentication error message from RER
    """
    # Determine recipient: use user email in production, test email for local dev
    # Check if running in local test mode (RER_LOCAL_TEST env var)
    is_local_test = os.getenv("RER_LOCAL_TEST") is not None
    recipient = "ap.johnston@outlook.com" if is_local_test else user_email

    subject = "RER Scraper Authentication Failed - MFA Retrieval Failed"

    html_body = f"""
    <html>
    <body>
        <h2>RER Scraper Authentication Failure</h2>
        <p><strong>Automatic login failed for:</strong> {user_email}</p>
        <p>Error message: <strong>{error_message}</strong></p>
        <p>This probably means that there is a problem with the SMS message forwarding that means the MFA code is not reaching energy.source.notifications@gmail.com.<br>You should fix the issue ASAP, as the scraper will continue to fail until the MFA code can be retrieved.</p>
        <hr>
        <p><em>This is an automated notification from the RER Session Auth Lambda.</em></p>
    </body>
    </html>
    """

    payload = {
        "to": recipient,
        "cc": "",
        "bcc": "",
        "from": "RER Scraper Monitor <noreply@rer-scraper.monitor>",
        "subject": subject,
        "html": html_body,
    }

    try:
        log.info("Sending MFA retrieval failure notification to %s", recipient)
        response = requests.post(
            MAKE_EMAILER_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        log.info("MFA retrieval failure notification sent successfully")
    except requests.RequestException as e:
        log.error("Failed to send MFA retrieval failure notification: %s", e)
        # Don't re-raise - we still want to raise the original auth error


def _build_session(cookies: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(RER_DEFAULT_HEADERS)
    if cookies:
        session.cookies.update(cookies)
    return session


def _get_gmail_messages() -> list[GmailMessage]:
    """Retrieve Gmail messages received by energy.source.notifications@gmail.com in the last day that include the text 'New message from msverify' in the subject"""
    api_key = os.getenv("MAKE_API_KEY")
    if not api_key:
        raise MissingConfigurationError(
            "Set MAKE_API_KEY environment variable to retrieve Gmail messages."
        )
    try:
        url = MAKE_GET_MFA_EMAILS_URL
        response = requests.post(url, headers={"x-make-apikey": api_key})
        if response.status_code != 200:
            raise requests.HTTPError(
                f"Failed to retrieve Gmail messages: {response.status_code}. Error: {response.text}"
            )
        log.debug(f"Response from Make.com: {response.text[:200]}...")
        result = response.json()
        emails: list[GmailMessage] = json.loads(result["json"])
        log.debug(f"Retrieved {len(emails)} emails")
    except requests.HTTPError as e:
        log.error(f"Error fetching emails: {e}")
        raise
    except Exception as e:
        log.error(f"Unexpected error fetching emails: {e}")
        raise
    if emails[0]["date"] is None:
        return (
            []
        )  # Make.com insists on parsing together at least one object even for no results

    return emails


def _retrieve_mfa_code(
    button_clicked_after: dt.datetime,
    max_retries: int,
    wait_between_retries: int,
) -> str:
    for retry_number in range(max_retries):
        log.info(
            "Attempting to retrieve MFA code (%s/%s)", retry_number + 1, max_retries
        )
        messages_today = _get_gmail_messages()
        uk_tz = ZoneInfo("Europe/London")
        messages_after_click = [
            message
            for message in messages_today
            if dt.datetime.fromisoformat(message["date"]).astimezone(uk_tz)
            > button_clicked_after
        ]

        for message in messages_after_click:
            body_text = message["html"]
            log.debug(body_text)
            if "RER-External-prd authentication" not in body_text:
                continue

            match = re.search(r"verification code (\d{6})", body_text)
            if match:
                log.info(
                    "Found a matching RER MFA email on attempt %s", retry_number + 1
                )
                return match.group(1)

        log.warning(
            "MFA email not found. Retrying in %s seconds.", wait_between_retries
        )
        sleep(wait_between_retries)

    raise TimeoutError(f"Failed to retrieve MFA code after {max_retries} attempts.")


# endregion helpers

# region exports


def are_cookies_valid(cookies: dict[str, str], timeout: int = 30) -> bool:
    if not cookies:
        return False

    try:
        response = _build_session(cookies).get(
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
            page.wait_for_load_state("networkidle")

            page.fill("#signInName", config.email)
            page.fill("#password", config.password)
            captcha_image_url_node = page.query_selector(
                "#captchaControlChallengeCode-img"
            )
            if not captcha_image_url_node:
                raise RuntimeError("Failed to locate CAPTCHA image on the page")

            captcha_image_url = captcha_image_url_node.get_attribute("src")
            if not captcha_image_url:
                raise RuntimeError("Failed to retrieve CAPTCHA image URL")

            captcha_solution = _solve_captcha(captcha_image_url)
            page.fill("#captchaControlChallengeCode", captcha_solution)

            # attempt sign in
            page.click("#next")
            page.wait_for_load_state("networkidle")

            # Wait for error messages to appear
            sleep(2)

            # check for captcha failure - error appears in specific p element
            # Selector from browser: #localAccountForm > div.entry > div.CaptchaControl.entry-item.captchaControlChallengeCode_section > div.error.itemLevel > p
            log.info("Checking for CAPTCHA error...")
            captcha_error_selector = "#localAccountForm > div.entry > div.CaptchaControl.entry-item.captchaControlChallengeCode_section > div.error.itemLevel > p"
            captcha_error_node = page.query_selector(captcha_error_selector)
            if captcha_error_node:
                captcha_error_text = captcha_error_node.text_content()
                log.info(f"CAPTCHA error text: {captcha_error_text}")
                if captcha_error_text:
                    log.error(f"Captcha error message: {captcha_error_text}")
                    captcha_max_retries = 3
                    retries = 0

                    while retries < captcha_max_retries:
                        log.info(
                            f"Captcha failed. Retrying... (attempt {retries + 1} of {captcha_max_retries})"
                        )
                        retries += 1

                        captcha_solution = _solve_captcha(captcha_image_url)

                        page.fill("#captchaControlChallengeCode", captcha_solution)
                        page.click("#next")
                        page.wait_for_load_state("networkidle")
                        sleep(2)

                        # Re-check for CAPTCHA error
                        captcha_error_node = page.query_selector(captcha_error_selector)
                        if not captcha_error_node:
                            log.info("No CAPTCHA error found - moving on")
                            break

                        captcha_error_text = captcha_error_node.text_content()
                        log.info(f"CAPTCHA still failed: {captcha_error_text}")

                    if retries >= captcha_max_retries:
                        log.error(
                            f"Maximum CAPTCHA retries of {captcha_max_retries} exceeded"
                        )
                        _send_password_failure_notification(
                            config.email, captcha_error_text or ""
                        )
                        raise ValueError(f"Authentication failed: {captcha_error_text}")

            # check for generic login errors (e.g., wrong password)
            # Password errors appear in p element within form error div
            login_error_node = page.query_selector(
                "#localAccountForm > div.entry > div.error.itemLevel > p"
            )

            if login_error_node:
                error_text = login_error_node.text_content()
                if error_text:
                    # Send notification before raising error
                    log.error(f"Authentication failed with message: {error_text}")
                    _send_password_failure_notification(config.email, error_text)
                    raise ValueError(f"Authentication failed: {error_text}")

            uk_tz = ZoneInfo("Europe/London")
            button_clicked_after = dt.datetime.now(uk_tz)
            log.info("Clicking to send MFA code")
            page.click("#readOnlyEmail_ver_but_send")
            page.wait_for_load_state("networkidle")

            sleep(config.wait_between_retries)
            try:
                mfa_code = _retrieve_mfa_code(
                    button_clicked_after=button_clicked_after,
                    max_retries=config.max_retries,
                    wait_between_retries=config.wait_between_retries,
                )
            except TimeoutError as e:
                _send_mfa_retrieval_failure_notification(
                    config.email,
                    str(e),
                )
                raise e

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
            sanitized_cookies = _sanitize_cookies(
                {cookie.get("name", ""): cookie.get("value", "") for cookie in cookies}
            )
            log.info("RER login produced %s cookies", len(sanitized_cookies))
            return sanitized_cookies
        finally:
            browser.close()


# endregion exports
