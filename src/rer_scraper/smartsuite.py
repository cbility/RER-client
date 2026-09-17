from __future__ import annotations

import logging
import os
from smartsuite_python import (
    SmartSuiteClient,
    FilterElement,
    FilterDateValue,
    FilterDateMode,
)
from dataclasses import asdict
from datetime import datetime

from rer_client.models import (
    CertificatesOverview,
    OrganisationDetail,
    OrganisationStation,
    OrganisationSummary,
    User,
)
from rer_scraper.models import ScraperOperations

logger = logging.getLogger(__name__)


class RERSmartSuiteClient(SmartSuiteClient):
    """Owns SmartSuite HTTP access and scraper-specific record mappings."""

    # record ids
    record_id_rer_scaper = (
        "6a7104dc65c1e43caf1f2792",
    )  # smartsuite record ID belonging to the record for the scraper

    # table ids
    table_id_scraper_job_configuration_table_id = "663d2313b4e7828a33b1ac07"
    table_id_ro_organisations = "665dc5a9eb40433ff6407de9"
    table_id_ro_logins = "652b1faba9847148f31cee2b"
    table_id_ro_stations = "652b1faba9847148f31cee2a"

    def __init__(self, account_id: str, api_token: str):
        self.ss = SmartSuiteClient(account_id, api_token)

    @classmethod
    def from_env(cls) -> "RERSmartSuiteClient":
        account_id = os.getenv("SMARTSUITE_ACCOUNT_ID")
        if account_id is None:
            raise ValueError("SMARTSUITE_ACCOUNT_ID is not included in .env file.")

        api_token = os.getenv("SMARTSUITE_API_TOKEN")
        if api_token is None:
            raise ValueError("SMARTSUITE_API_TOKEN is not included in .env file.")

        return cls(
            account_id=account_id,
            api_token=api_token,
        )

    # region getters

    def get_operations(self, launch_time: datetime) -> list[ScraperOperations]:
        """Return pending scraper work."""
        scraper_filter = FilterElement(
            field="s902579400",  # Scraper field
            comparison="is",
            value="6a7104dc65c1e43caf1f2792",  # RER Scraper record ID
        )
        next_run_filter = FilterElement(
            field="s8173a46ec",  # Run Next After field
            comparison="is_on_or_after",
            value=FilterDateValue(
                date_mode="exact_date", date_mode_value=launch_time.isoformat()
            ),
        )
        operations_records = self.ss.filter_records(
            table_id="663d2313b4e7828a33b1ac07",  # Scraper job configuration table
            fields_to_filter=[scraper_filter, next_run_filter],
        )

        operations: list[ScraperOperations] = []

        for record in operations_records:
            match (record["id"]):
                case "6a8328cb2f59c6c95139943d":  # data update record id
                    operations.append("refresh_data")
                case "6a832d732f59c6c951399446":  # certificate transfer record id
                    operations.append("transfer_certificates")

        return operations

    def get_current_organisations(self):
        current_organisations = self.ss.get_all_records(
            table_id=self.table_id_ro_organisations
        )
        return current_organisations

    def get_current_stations(self):
        current_organisations = self.ss.get_all_records(
            table_id=self.table_id_ro_stations
        )
        return current_organisations

    def get_organisation_id(self, organisation_record: dict):
        return organisation_record.get("s44395f753")

    def get_station_id(self, station_record: dict):
        return station_record.get("sb2a2fadfb")

    # endregion getters

    # region mappers

    def map_user(self, user: User):
        return {
            "scb73bd95a": {
                "first_name": user.full_name.split(" ")[0],
                "last_name": " ".join(user.full_name.split(" ")[1:]),
            },
            "sc87fbb8dc": [user.email],
            # TODO: get user phone number from /Account/EditPhoneNumber
        }

    def map_organisation(
        self,
        rer_organisation_summary: OrganisationSummary,
        rer_organisation_details: OrganisationDetail,
    ):
        ss_organisation = {
            "sde6082ea0": rer_organisation_summary.name,  # generator/company name
            "s44395f753": rer_organisation_summary.organisation_id,  # organisation id
            "s90b4a920a": rer_organisation_summary.type,
            "sf3acd7357": rer_organisation_summary.status,
            "s2cad6c1e7": ", ".join(rer_organisation_details.address),
            "s8102cbd5d": rer_organisation_details.contact.email,
            "s4e25eef9b": {
                "first_name": rer_organisation_details.contact.name.split(" ")[0],
                "last_name": " ".join(
                    rer_organisation_details.contact.name.split(" ")[1:]
                ),
            },
            "s90b4a920a": rer_organisation_details.type,
            "s8aaed9a66": rer_organisation_summary.user_status,
        }
        return ss_organisation

    def map_station(
        self,
        rer_station: OrganisationStation,
        certificates: list[CertificatesOverview],
        update_time: datetime,
    ):
        ro_scheme_status = "Not Set"
        rego_scheme_status = "Not Set"
        for scheme in rer_station.scheme_statuses:
            if scheme.scheme == "RO":
                ro_scheme_status = scheme.status
            elif scheme.scheme == "REGO":
                rego_scheme_status = scheme.status

        for cert in certificates:
            pass  # TODO: add certificate statistics to station mapping
        ss_station = {
            "sb2a2fadfb": rer_station.station_id,  # station id
            "sde6082ea0": rer_station.station_name,  # station name
            "sf6261a94b": ro_scheme_status,  # RO scheme status
            "sxyont8b": rego_scheme_status,  # REGO scheme status
            "secb786709": rer_station.country,  #  country
            "secb786709": rer_station.technology_group,  # technology
            "s9c6cfc3d3": {"date": update_time.isoformat()},  # statistics last updated
            "sqih0nxo": {"date": update_time.isoformat()},  # oldest regos not issued
        }
        return ss_station

    # endregion mappers

    # region changes

    def update_user(self, user: dict):
        """Update an existing user record in SmartSuite."""
        logger.info(f"Updating user in SmartSuite...")
        logger.debug(f"User to update: {user}")

        try:
            result = self.ss.bulk_update_records(
                table_id=self.table_id_ro_logins, records=[user]
            )
            logger.info(f"Successfully updated user")
            return result
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            logger.error(f"Failed record: {user}")
            raise

    def update_organisations(self, update_orgs: list[dict]):
        """Update existing organisation records in SmartSuite."""
        logger.info(f"Updating {len(update_orgs)} organisation(s) in SmartSuite...")
        logger.debug(f"Organisations to update: {update_orgs}")

        try:
            result = self.ss.bulk_update_records(
                table_id=self.table_id_ro_organisations, records=update_orgs
            )
            logger.info(f"Successfully updated {len(update_orgs)} organisation(s)")
            return result
        except Exception as e:
            logger.error(f"Failed to update organisations: {e}")
            logger.error(f"Failed records: {update_orgs}")
            raise

    def create_organisations(self, new_orgs: list[dict]):
        """Create new organisation records in SmartSuite."""
        logger.info(f"Creating {len(new_orgs)} new organisation(s) in SmartSuite...")
        logger.debug(f"Organisations to create: {new_orgs}")

        try:
            result = self.ss.bulk_add_new_records(
                table_id=self.table_id_ro_organisations, records=new_orgs
            )
            logger.info(f"Successfully created {len(new_orgs)} organisation(s)")
            return result
        except Exception as e:
            logger.error(f"Failed to create organisations: {e}")
            logger.error(f"Failed records: {new_orgs}")
            raise
