# region imports
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol
from datetime import datetime
from unittest import result

import requests

from rer_client import RERClient
from rer_client.models import (
    CertificatesOverview,
    OrganisationStation,
    OrganisationSummary,
    OrganisationDetail,
    User,
)
from rer_scraper.models import (
    RefreshResult,
    ScraperOperations,
    ScraperResult,
    TransferInstruction,
    TransferPreparationResult,
)
from rer_scraper.smartsuite import RERSmartSuiteClient

import logging

# endregion imports

# region configuration
logger = logging.getLogger(__name__)

# endregion configuration


# region support classes


@dataclass
class REROrganisation:
    """Container for organisation summary and details"""

    org_summary: OrganisationSummary
    org_detail: OrganisationDetail


class RetryInvoker(Protocol):
    """
    Protocol defining a contract for triggering retry executions of the scraper Lambda function.

    This is used when the session-auth API returns a 202 Accepted response, indicating that
    cookies are not yet ready. The RetryInvoker schedules an asynchronous retry of the scraper
    without blocking the current execution.

    The Protocol pattern allows dependency injection, enabling different implementations
    for production (Boto3RetryInvoker in handler.py) and testing (StubRetryInvoker in tests).
    """

    def invoke(self, function_name: str, payload: dict[str, Any]) -> None:
        """
        Invoke a retry of the scraper function.

        Args:
            function_name: The name of the Lambda function to invoke.
            payload: The payload to pass to the function, typically including retry flags.
        """
        ...  # implemented in lambda handler


class SessionAuthClient:
    """
    Client for retrieving RER session cookies from the session-auth API.

    This client communicates with the session-auth Lambda service to obtain
    authenticated cookies for accessing the RER portal. When cookies are not
    yet ready (e.g., during OAuth flow), the API returns a 202 Accepted status,
    and this client returns None to signal that a retry should be scheduled.
    """

    def __init__(self, api_url: str, api_key: str, timeout: int = 30):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def get_cookies(self) -> dict[str, str] | None:
        response = requests.get(
            self.api_url,
            headers={"x-api-key": self.api_key},
            timeout=self.timeout,
        )
        if response.status_code == 202:
            return None
        response.raise_for_status()
        cookies = response.json().get("cookies")
        if not isinstance(cookies, dict):
            raise ValueError("Session-auth API response did not include cookies.")
        return {str(name): str(value) for name, value in cookies.items()}


# endregion support classes

# region main class


class RERScraperService:
    """
    Main service orchestrating RER data scraping and SmartSuite synchronization.

    This service coordinates the following operations:
    - Retrieving session cookies via the SessionAuthClient
    - Fetching current data from RER (organisations, stations, certificates)
    - Updating SmartSuite records with the latest RER data
    - Preparing certificate transfers between organisations
    - Scheduling retries when session authentication is pending

    The service uses dependency injection for flexibility and testability:
    - RERSmartSuiteClient for SmartSuite API interactions
    - SessionAuthClient for RER session management
    - RetryInvoker for scheduling retry executions
    - client_factory for creating RER client instances
    """

    # region initialisation

    def __init__(
        self,
        smartsuite: RERSmartSuiteClient,
        session_auth: SessionAuthClient,
        retry_invoker: RetryInvoker,
        function_name: str,
        client_factory: Callable[[dict[str, str]], RERClient] = RERClient,
        dry_run: bool = False,
    ):
        self.smartsuite = smartsuite
        self.session_auth = session_auth
        self.retry_invoker = retry_invoker
        self.function_name = function_name
        self.client_factory = client_factory
        self.dry_run = dry_run

    # endregion initialisation
    # region orchestrator

    def run(self, schedule_retry: bool = True) -> tuple[int, ScraperResult | None]:
        run_start = datetime.now()
        operations = self.smartsuite.get_operations(run_start)
        if len(operations) == 0:
            return 204, None  # successful run but no tasks scheduled

        cookies = self.session_auth.get_cookies()
        if cookies is None:
            if schedule_retry:
                self.retry_invoker.invoke(self.function_name, {"retry_scrape": True})
            return 202, None

        rer = self.client_factory(cookies)
        result = ScraperResult()
        if "refresh_data" in operations:
            user, organisations, stations, certificates = self.get_current_data(rer)
            self.update_rer_user(user)
            self.update_rer_organisations(organisations)
            # TODO: update stations

        if "transfer_certificates" in operations:
            raise NotImplementedError

        return 200, result

    def get_current_data(self, rer: RERClient):

        user = rer.get_user()
        logger.info(f"Fetched user: {user}")

        organisation_summaries = rer.get_user_org_summary()
        logger.info(
            f"Fetched {len(organisation_summaries)} organisations for logged in user. Getting extra info for each organisation..."
        )
        organisations: list[REROrganisation] = []
        for org_summary in organisation_summaries:
            org_detail = rer.get_organisation_detail(org_summary.organisation_id)
            organisations.append(REROrganisation(org_summary, org_detail))

        # logger.debug(f"Organisations: {organisations}")
        organisation_stations = [
            rer.get_organisation_stations(org.org_summary.organisation_id)
            for org in organisations
        ]
        logger.info(f"Fetched stations for {len(organisation_stations)} organisations")
        # logger.debug(f"Stations: {organisation_stations}")
        organisation_certificates = [
            rer.get_organisation_certificates(org.org_summary.organisation_id)
            for org in organisations
        ]
        logger.info(
            f"Fetched certificates for {len(organisation_certificates)} organisations"
        )
        # logger.debug(f"Certificates: {organisation_certificates}")

        # endregion organisations

        return user, organisations, organisation_stations, organisation_certificates

    # endregion orchestrators
    # region data update helpers

    def update_rer_organisations(
        self,
        organisations: list[REROrganisation],
    ):
        """
        Updates organisation and station records on SmartSuite with the passed details.
        Updates records if they already exist, otherwise creates new records.
        Certificate information is used to create statistics and stores at the station level.
        """

        ss_organisations = (
            [] if self.dry_run else self.smartsuite.get_current_organisations()
        )

        # spit records into updates and inserts

        update_orgs = []
        insert_orgs = []
        logger.info(f"Processing {len(organisations)} organisations")
        for org in organisations:
            logger.debug(f"   {org}")
            ss_org_record = next(
                (
                    ss_org
                    for ss_org in ss_organisations
                    if self.smartsuite.get_organisation_id(ss_org)
                    == org.org_summary.organisation_id
                ),
                None,
            )
            if ss_org_record is not None:
                update_orgs.append(
                    {
                        **self.smartsuite.map_organisation(
                            org.org_summary, org.org_detail
                        ),
                        "id": ss_org_record["id"],
                    }
                )
            else:
                insert_orgs.append(
                    self.smartsuite.map_organisation(org.org_summary, org.org_detail)
                )

        if update_orgs:
            logger.info(f"{len(update_orgs)} organisations to UPDATE")
            for org in update_orgs:
                logger.debug(f"  {org}")

        if insert_orgs:
            logger.info(f"{len(insert_orgs)} organisations to CREATE")
            for org in insert_orgs:
                logger.debug(f"  {org}")

        if not self.dry_run:
            self.smartsuite.update_organisations(update_orgs)
            self.smartsuite.create_organisations(insert_orgs)
        else:
            logger.warning("Dry run mode: skipping SmartSuite writes")

    def update_rer_user(self, user: User) -> None:
        logger.info(f"Updating RER user: {user}")
        if not self.dry_run:
            self.smartsuite.update_user(self.smartsuite.map_user(user))
        else:
            logger.warning("Dry run mode: skipping SmartSuite user update")

    # endregion data refresh helpers

    # region cert transfer helpers

    def prepare_transfer(
        self,
        client: RERClient,
        transfer: TransferInstruction,
    ) -> TransferPreparationResult:
        source_station = client.get_station(transfer.source_station_id)
        source_organisation_id = self._find_source_organisation_id(
            client, transfer.source_station_id
        )
        recipient = client.find_transfer_organisation(
            source_organisation_id,
            transfer.destination_generator_reference,
            transfer.certificate_type,
        )
        if recipient is None:
            return TransferPreparationResult(
                source_station_id=transfer.source_station_id,
                destination_generator_reference=transfer.destination_generator_reference,
                selected=False,
                reason="destination generator was not found",
            )

        try:
            client.select_certificates(
                source_organisation_id,
                transfer.certificate_type,
                source_station.station_name,
                transfer.start_period,
                transfer.end_period,
            )
        except ValueError as exc:
            if str(exc).startswith("No ") and "certificate ranges match" in str(exc):
                return TransferPreparationResult(
                    source_station_id=transfer.source_station_id,
                    destination_generator_reference=transfer.destination_generator_reference,
                    selected=False,
                    reason="no matching certificate ranges",
                )
            raise

        return TransferPreparationResult(
            source_station_id=transfer.source_station_id,
            destination_generator_reference=transfer.destination_generator_reference,
            selected=True,
        )

    @staticmethod
    def _find_source_organisation_id(rer: RERClient, station_id: str) -> str:
        for organisation in rer.get_user_org_summary():
            stations = rer.get_organisation_stations(organisation.organisation_id)
            if any(station.station_id == station_id for station in stations):
                return organisation.organisation_id
        raise ValueError(
            f"Station {station_id!r} is not available to the authenticated user."
        )

    # endregion certificate transfer helpers
    # region exported helpers

    @staticmethod
    def parse_scraper_result(result: ScraperResult | None) -> str:
        return json.dumps(asdict(result)) if result else "{}"

    # endregion exported helpers


# endregion main class
