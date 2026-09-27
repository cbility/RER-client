# region imports
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol
from datetime import datetime
from unittest import result
from itertools import chain  # for flattening nested lists

import requests

from rer_client import RERClient
from rer_client.models import (
    CertificateTypeSummary,
    OrganisationCertificateGroup,
    OrganisationStation,
    OrganisationStationList,
    OrganisationSummary,
    OrganisationDetail,
    OrganisationOutputSubmissionGroup,
    StationOutputSubmission,
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
        ss_login_record_id: str,
        client_factory: Callable[[dict[str, str]], RERClient] = RERClient,
        dry_run: bool = False,
    ):
        self.smartsuite = smartsuite
        self.session_auth = session_auth
        self.retry_invoker = retry_invoker
        self.function_name = function_name
        self.client_factory = client_factory
        self.dry_run = dry_run
        self.ss_login_record_id = ss_login_record_id

    # endregion initialisation
    # region orchestration

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
            user, organisations, stations, certificates, output_periods = (
                self.get_current_data(rer)
            )
            self.update_rer_user(user)
            self.update_rer_organisations(organisations, self.ss_login_record_id)
            self.update_rer_stations(stations, certificates, output_periods, run_start)

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
        organisation_stations_lists = [
            rer.get_organisation_stations(org.org_summary.organisation_id)
            for org in organisations
        ]

        # logger.debug(f"Stations: {organisation_stations}")
        organisation_certificates = [
            rer.get_organisation_certificates(org.org_summary.organisation_id)
            for org in organisations
        ]

        # logger.debug(f"Certificates: {organisation_certificates}")

        output_periods = [
            rer.get_organisation_output_data(org.org_summary.organisation_id)
            for org in organisations
        ]

        logger.info(
            f"Fetched data for {len(organisation_stations_lists)} organisations"
        )

        return (
            user,
            organisations,
            organisation_stations_lists,
            organisation_certificates,
            output_periods,
        )

    # endregion orchestrators
    # region data update helpers

    def update_rer_organisations(
        self,
        organisations: list[REROrganisation],
        ss_user_record_id: str,
    ):
        """
        Updates organisation records on SmartSuite with the passed details.
        Updates records if they already exist, otherwise creates new records.
        """

        ss_organisations = (
            [] if self.dry_run else self.smartsuite.get_current_organisations()
        )

        # spit records into updates and inserts

        update_orgs = []
        insert_orgs = []
        logger.info(f"Processing {len(organisations)} organisations")
        for org in organisations:
            logger.info(
                f"  Processing organisation: {org.org_summary.organisation_id} {org.org_summary.name}"
            )
            logger.debug(f"Full organisation object: {org}")
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
                            org.org_summary,
                            org.org_detail,
                            ss_user_record_id,
                        ),
                        "id": ss_org_record["id"],
                    }
                )
            else:
                insert_orgs.append(
                    self.smartsuite.map_organisation(
                        org.org_summary, org.org_detail, ss_user_record_id
                    )
                )
        logger.info(f"{len(update_orgs)} organisations to UPDATE")
        for org in update_orgs:
            logger.debug(f"{json.dumps(org, indent=2)}")

        logger.info(f"{len(insert_orgs)} organisations to CREATE")

        for org in insert_orgs:
            logger.debug(f"{json.dumps(org, indent=2)}")

        if not self.dry_run:
            self.smartsuite.update_organisations(update_orgs)
            self.smartsuite.create_organisations(insert_orgs)
        else:
            logger.warning("Dry run mode: skipping SmartSuite organisation writes")

    def update_rer_user(self, user: User) -> None:
        logger.info(f"Updating RER user: {user}")
        if not self.dry_run:
            self.smartsuite.update_user(self.smartsuite.map_user(user))
        else:
            logger.warning("Dry run mode: skipping SmartSuite user update")

    def update_rer_stations(
        self,
        organisation_station_groups: list[OrganisationStationList],
        organisation_certificates: list[OrganisationCertificateGroup],
        organisation_output_periods_groups: list[OrganisationOutputSubmissionGroup],
        run_start: datetime,
    ):
        """
        Updates station records on SmartSuite with the passed details.
        Updates records if they already exist, otherwise creates new records.
        Certificate information is used to create statistics and is stored at the station level.
        """
        # spit records into updates and inserts
        update_stations = []
        insert_stations = []
        logger.info(
            f"Processing stations for {len(organisation_station_groups)} organisations"
        )

        # get existing station records from SmartSuite
        ss_stations = [] if self.dry_run else self.smartsuite.get_current_stations()

        for org_station_group in organisation_station_groups:
            org_certificate_summary = next(
                (
                    cert_group
                    for cert_group in organisation_certificates
                    if cert_group.organisation_id == org_station_group.organisation_id
                ),
            )
            org_output_periods = next(
                (
                    organisation_period_group
                    for organisation_period_group in organisation_output_periods_groups
                    if organisation_period_group.organisation_id
                    == org_station_group.organisation_id
                ),
            )

            logger.info(
                f"Processing {len(org_station_group.stations)} stations for organisation {org_station_group.organisation_id}"
            )

            for station in org_station_group.stations:
                logger.debug(f"   {station}")
                # Match by station_name since station_id is not available in output submissions view
                station_output_periods = [
                    op
                    for op in org_output_periods.submissions
                    if op.station_name == station.station_name
                ]
                ss_station_record = next(
                    (
                        ss_station
                        for ss_station in ss_stations
                        if self.smartsuite.get_station_id(ss_station)
                        == station.station_id
                    ),
                    None,
                )
                if ss_station_record is not None:
                    update_stations.append(
                        {
                            **self.smartsuite.map_station(
                                rer_station=station,
                                output_periods=station_output_periods,
                                # certificates=certificates,
                                update_time=run_start,
                            ),
                            "id": ss_station_record["id"],
                        }
                    )
                else:
                    insert_stations.append(
                        self.smartsuite.map_station(
                            rer_station=station,
                            output_periods=station_output_periods,
                            # certificates=certificates,
                            update_time=run_start,
                        )
                    )

        logger.info(f"{len(update_stations)} stations to UPDATE")
        for station in update_stations:
            logger.debug(f"{json.dumps(station, indent=2)}")

        logger.info(f"{len(insert_stations)} stations to CREATE")
        for station in insert_stations:
            logger.debug(f"{json.dumps(station, indent=2)}")

        if not self.dry_run:
            self.smartsuite.update_stations(update_stations)
            self.smartsuite.create_stations(insert_stations)
        else:
            logger.warning("Dry run mode: skipping SmartSuite station writes")

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
            station_list = rer.get_organisation_stations(organisation.organisation_id)
            if any(
                station.station_id == station_id for station in station_list.stations
            ):
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
