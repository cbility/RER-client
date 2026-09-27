# region imports

import calendar
import logging  # for logging

import requests  # lighttweight web requests

from selectolax.parser import HTMLParser  # for parsing HTML

import json  # for saving cookies
import re  # for pagination parsing
import math  # for pagination calculation

from rer_client import parsing as rer_parsing
from rer_client.models import OrganisationOutputSubmissionList

# endregion imports

# region config

# configure logging
log = logging.getLogger(__name__)

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

# region class


class RERClient:
    """Client for making authenticated requests to the RER portal.

    Params:
        auth_cookies: dict of cookies to use for authentication.
        headers: Optional dict of headers to use for requests. Defaults to RER_DEFAULT_HEADERS.
    """

    session: requests.Session
    base_url = "https://rer.ofgem.gov.uk/"

    def __init__(self, auth_cookies: dict, headers: dict = RER_DEFAULT_HEADERS):
        self.auth_cookies = auth_cookies
        self.headers = headers

        self.authenticate(auth_cookies, headers)

    def get_cookies(self) -> dict:
        """Get current session cookies."""
        return self.session.cookies.get_dict()

    def authenticate(
        self, auth_cookies: dict, headers: dict = RER_DEFAULT_HEADERS
    ) -> None:
        """Authenticate with RER portal and set session.

        Creates a session with the provided cookies.
        Throws an error if cookies are not provided.
        """

        if not auth_cookies:
            raise ValueError("Authentication cookies must be provided.")

        session = requests.Session()
        session.headers.update(headers)
        session.cookies.update(auth_cookies)
        self.session = session

        try:
            user = self.get_user()
        except requests.exceptions.ConnectionError as e:
            raise ValueError("Authentication cookies could not be validated.") from e

        log.info(
            f"Authenticated as {user.email} ({user.full_name}) using provided cookies."
        )

    def _request(
        self, endpoint: str, method: str = "GET", **kwargs
    ) -> requests.Response:
        """Make an authenticated request to the RER portal."""
        url = self.base_url + endpoint.lstrip("/")
        response = self.session.request(method, url, **kwargs)
        if response.status_code == 200:
            return response
        elif response.status_code == 403:
            raise requests.exceptions.HTTPError(
                f"Request refused: {response.status_code}. This usually means the RER server is unavailable at this time."
            )
        else:
            log.error(
                f"Unexpected response when making request to {endpoint}: {response.status_code} - {response.text}"
            )
            response.raise_for_status()
        return response

    # region getters
    def get_user(self) -> rer_parsing.User:
        """GET /User - Returns user dashboard with stats and organisation list."""
        response = self._request("User")
        return rer_parsing._parse_user(response.text)

    def get_user_org_summary(
        self,
        sort_field: str | None = None,
        sort_direction: str | None = None,
    ) -> list[rer_parsing.OrganisationSummary]:
        """GET /User - Returns all organisations for the authenticated user across all pages."""
        params: dict = {"pageNumber": 1}
        if sort_field:
            params["sortField"] = sort_field
        if sort_direction:
            params["sortDirection"] = sort_direction

        response = self._request("User", params=params)
        first_html = response.text

        # Determine total pages from pagination results summary
        tree = HTMLParser(first_html)
        total_pages = 1
        results_el = tree.css_first(".moj-pagination__results")
        if results_el:
            m = re.search(
                r"Showing\s+(\d+)\s+to\s+(\d+)\s+of\s+(\d+)",
                results_el.text(strip=True),
            )
            if m:
                start, end, total = int(m.group(1)), int(m.group(2)), int(m.group(3))
                page_size = end - start + 1
                total_pages = math.ceil(total / page_size)

        pages = [first_html]
        for page_num in range(2, total_pages + 1):
            params["pageNumber"] = page_num
            pages.append(self._request("User", params=params).text)

        return rer_parsing._parse_user_organisations(pages)

    def get_organisation_detail(
        self, organisation_id: str
    ) -> rer_parsing.OrganisationDetail:
        """GET /Organisations/OrganisationReview/{organisationId} - Returns organisation details."""
        response = self._request(f"Organisations/OrganisationReview/{organisation_id}")
        return rer_parsing._parse_organisation(response.text)

    def get_organisation_output_data_tasks(
        self,
        organisation_id: str,
        statuses: list[str] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page_number: int = 1,
    ) -> rer_parsing.OutputDataTaskList:
        """GET /Organisations/{organisationId}/Tasks/OutputData - Returns output data tasks."""
        params: dict = {"pageNumber": page_number}
        if statuses:
            params["Statuses"] = statuses
        if sort_field:
            params["sortField"] = sort_field
        if sort_direction:
            params["sortDirection"] = sort_direction
        response = self._request(
            f"Organisations/{organisation_id}/Tasks/OutputData", params=params
        )
        return rer_parsing._parse_output_data_tasks(response.text, organisation_id)

    def get_organisation_output_data(
        self,
        organisation_id: str,
    ) -> OrganisationOutputSubmissionList:
        """GET /Organisations/{organisationId}/Output - Returns all station output submissions.

        Fetches all output submissions for an organisation across all pages.
        Optionally filters by a specific station.

        Args:
            organisation_id: Organisation identifier
            station_id: Optional station UUID to filter by

        Returns:
            List of StationOutputSubmission records (filtered by station if provided)

        Example:
            # Get all submissions for an organisation
            submissions = client.get_organisation_output_data("GEN0213742")

            # Get submissions for a specific station only
            submissions = client.get_organisation_output_data(
                "GEN0213742",
                station_id="469C9786-148B-4FFA-9E4B-0C30B0004AF3"
            )
        """

        all_submissions: list[rer_parsing.StationOutputSubmission] = []
        page_number = 1

        while True:
            try:
                params = {"pageNumber": page_number}

                response = self._request(
                    f"Organisations/{organisation_id}/Output",
                    params=params,
                )
                result = rer_parsing._parse_station_output_submissions(
                    response.text, organisation_id
                )

                if not result.submissions:
                    break

                all_submissions.extend(result.submissions)
                page_number += 1
            except Exception:
                # No more pages or error fetching
                break

        return OrganisationOutputSubmissionList(
            organisation_id=organisation_id, submissions=all_submissions
        )

    def get_organisation_station_declaration_tasks(
        self,
        organisation_id: str,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page_number: int = 1,
    ) -> rer_parsing.StationDeclarationTaskList:
        """GET /Organisations/{organisationId}/Tasks/StationDeclarations - Returns station declaration tasks."""
        params: dict = {"pageNumber": page_number}
        if sort_field:
            params["sortField"] = sort_field
        if sort_direction:
            params["sortDirection"] = sort_direction
        response = self._request(
            f"Organisations/{organisation_id}/Tasks/StationDeclarations", params=params
        )
        return rer_parsing._parse_station_declaration_tasks(
            response.text, organisation_id
        )

    def get_organisation_station_declarations(
        self,
        organisation_id: str,
    ) -> rer_parsing.StationDeclarationList:
        """GET /Organisations/{organisationId}/StationDeclarations - Returns station declarations."""
        response = self._request(f"Organisations/{organisation_id}/StationDeclarations")
        return rer_parsing._parse_station_declarations(response.text, organisation_id)

    def get_organisation_stations(
        self, organisation_id: str
    ) -> rer_parsing.OrganisationStationList:
        """GET /Organisations/{organisationId}/Stations - Returns list of stations for the organisation."""
        response = self._request(f"Organisations/{organisation_id}/Stations")
        stations = rer_parsing._parse_organisation_stations(
            response.text, organisation_id
        )

        return rer_parsing.OrganisationStationList(
            organisation_id=organisation_id, stations=stations
        )

    def get_station(self, station_id: str) -> rer_parsing.StationDetail:
        """GET /Organisations/Stations/{stationId} - Returns full station detail."""
        response = self._request(f"Organisations/Stations/{station_id}")
        return rer_parsing._parse_station(response.text, station_id)

    def find_transfer_organisation(
        self,
        organisation_id: str,
        recipient_reference: str,
        cert_type: str = "REGO",
    ) -> "rer_parsing.OrganisationSearchResult | None":
        """POST /Organisations/{organisationId}/Certificates/{certType}/FindOrganisation
        Searches for an organisation by reference. Returns the matched organisation or None.
        This is a read-only search — no certificates are transferred.
        """
        get_resp = self._request(
            f"Organisations/{organisation_id}/Certificates/{cert_type}/FindOrganisation"
        )
        token_el = HTMLParser(get_resp.text).css_first(
            "input[name=__RequestVerificationToken]"
        )
        csrf = token_el.attrs.get("value", "") if token_el else ""
        post_resp = self.session.post(
            self.base_url
            + f"Organisations/{organisation_id}/Certificates/{cert_type}/FindOrganisation",
            data={
                "RecipientOrganisationReference": recipient_reference,
                "__RequestVerificationToken": csrf,
            },
        )
        post_resp.raise_for_status()
        return rer_parsing._parse_find_organisation(post_resp.text)

    def get_organisation_certificates(
        self, organisation_id: str
    ) -> rer_parsing.OrganisationCertificates:
        """GET /Organisations/{organisationId}/Certificates - Returns certificates overview."""
        response = self._request(f"Organisations/{organisation_id}/Certificates")
        return rer_parsing._parse_certificates_overview(response.text, organisation_id)

    def get_organisation_certificates_breakdown(
        self,
        organisation_id: str,
        cert_type: str,
    ) -> rer_parsing.CertificateBreakdown:
        """GET /Organisations/{organisationId}/Certificates/{certType}/Breakdown - Returns certificate breakdown."""
        response = self._request(
            f"Organisations/{organisation_id}/Certificates/{cert_type}/Breakdown"
        )
        return rer_parsing._parse_certificate_breakdown(
            response.text, organisation_id, cert_type
        )

    def select_certificates(
        self,
        organisation_id: str,
        cert_type: str,
        station: str,
        start_period: str,
        end_period: str,
    ) -> None:
        """Select certificate ranges for a station over an inclusive period range.

        The portal selection is shared state. To prevent an unintended transfer,
        this method refuses to alter an existing selection.
        """
        cert_type = cert_type.upper()
        if cert_type not in {"ROC", "REGO"}:
            raise ValueError("cert_type must be either 'ROC' or 'REGO'.")

        try:
            start_month, start_year = start_period.split()
            end_month, end_year = end_period.split()
            start_index = (
                int(start_year),
                list(calendar.month_abbr).index(start_month),
            )
            end_index = (int(end_year), list(calendar.month_abbr).index(end_month))
        except (ValueError, IndexError):
            raise ValueError(
                "Periods must use the format 'Mon YYYY', for example 'Apr 2025'."
            ) from None
        if start_index > end_index:
            raise ValueError("start_period must not be after end_period.")

        endpoint = f"Organisations/{organisation_id}/Certificates/{cert_type}/Breakdown"
        response = self._request(endpoint)
        tree = HTMLParser(response.text)

        if tree.css_first("button[name=removeId]"):
            raise ValueError(
                "Certificates are already selected in the portal. Clear the existing selection before selecting a range."
            )

        matches: list[str] = []
        for row in tree.css("table tr"):
            cells = row.css("td")
            selection = row.css_first("input[name=selectedCertificates]")
            if len(cells) >= 6 and selection and cells[2].text(strip=True) == station:
                try:
                    month, year = cells[4].text(strip=True).split()
                    period_index = (int(year), list(calendar.month_abbr).index(month))
                except (ValueError, IndexError):
                    continue
                if start_index <= period_index <= end_index:
                    certificate_id = selection.attrs.get("value")
                    if certificate_id:
                        matches.append(certificate_id)

        if not matches:
            raise ValueError(
                f"No {cert_type} certificate ranges match station {station!r} between "
                f"{start_period!r} and {end_period!r}."
            )

        token_el = tree.css_first("input[name=__RequestVerificationToken]")
        csrf = token_el.attrs.get("value") if token_el else None
        if not csrf:
            raise ValueError(
                "Certificate selection form did not include a verification token."
            )

        self._request(
            endpoint,
            method="POST",
            data={
                "selectedCertificates": matches,
                "addSelected": "addSelected",
                "__RequestVerificationToken": csrf,
            },
        )

    def get_organisation_certificates_history(
        self,
        organisation_id: str,
        cert_type: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> rer_parsing.CertificateHistory:
        """GET /Organisations/{organisationId}/Certificates/{certType}/History - Returns certificate transaction history."""
        params: dict = {}
        if from_date:
            params["fromDate"] = from_date
        if to_date:
            params["toDate"] = to_date
        response = self._request(
            f"Organisations/{organisation_id}/Certificates/{cert_type}/History",
            params=params,
        )
        return rer_parsing._parse_certificate_history(
            response.text, organisation_id, cert_type
        )

    # endregion getters


# endregion class

# region testing

if __name__ == "__main__":

    def _load_cookies(cookies_file="../rer_cookies.json") -> dict:
        """Load saved cookies."""
        try:
            with open(cookies_file) as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Cookies file not found at {cookies_file}. Please authenticate to create it."
            )

    logging.basicConfig(level=logging.DEBUG)  # debug logging for testing

    cookies = _load_cookies()
    log.debug("Loaded cookies from file")
    rer = RERClient(auth_cookies=cookies)


# endregion testing
