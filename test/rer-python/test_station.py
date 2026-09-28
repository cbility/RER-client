"""Tests for RERClient.get_station() - GET /Organisations/Stations/{stationId}"""

import json
from dataclasses import asdict
import pytest

from rer_client.models import StationDetail

STATION_ID = "E7F48B1B-C6E3-44D6-87FE-5900C42B7229"  # Updated to match cached data from GEN0212970


@pytest.fixture(scope="module")
def station(rer):
    return rer.get_station(STATION_ID)


def test_returns_dict(station):
    assert isinstance(station, StationDetail)


def test_station_id_matches(station):
    assert station["station_id"].upper() == STATION_ID.upper()


def test_station_name_nonempty(station):
    assert isinstance(station["station_name"], str) and len(station["station_name"]) > 0


def test_organisation_name_nonempty(station):
    assert (
        isinstance(station["organisation_name"], str)
        and len(station["organisation_name"]) > 0
    )


def test_country_nonempty(station):
    assert isinstance(station["country"], str) and len(station["country"]) > 0


def test_commissioning_date_nonempty(station):
    assert (
        isinstance(station["commissioning_date"], str)
        and len(station["commissioning_date"]) > 0
    )


def test_total_installed_capacity_nonempty(station):
    assert (
        isinstance(station["total_installed_capacity"], str)
        and len(station["total_installed_capacity"]) > 0
    )


def test_technology_group_nonempty(station):
    assert (
        isinstance(station["technology_group"], str)
        and len(station["technology_group"]) > 0
    )


def test_address_nonempty(station):
    assert isinstance(station["address"], list)
    # Address can have variable number of lines depending on HTML structure
    # Each address line should be a string
    for line in station["address"]:
        assert isinstance(line, str)


def test_scheme_accreditations_is_list(station):
    assert isinstance(station["scheme_accreditations"], list)


def test_scheme_accreditations_nonempty(station):
    assert len(station["scheme_accreditations"]) > 0


def test_each_accreditation_has_required_fields(station):
    for acc in station["scheme_accreditations"]:
        assert isinstance(acc["scheme"], str) and len(acc["scheme"]) > 0
        assert (
            isinstance(acc["accreditation_reference"], str)
            and len(acc["accreditation_reference"]) > 0
        )
        assert (
            isinstance(acc["application_date"], str)
            and len(acc["application_date"]) > 0
        )
        assert isinstance(acc["effective_from"], str) and len(acc["effective_from"]) > 0
        assert isinstance(acc["status"], str) and len(acc["status"]) > 0


def test_station_capacities_is_list(station):
    assert isinstance(station["station_capacities"], list)


def test_station_capacities_nonempty(station):
    assert len(station["station_capacities"]) > 0


def test_each_capacity_has_required_fields(station):
    for cap in station["station_capacities"]:
        assert isinstance(cap["capacity_type"], str) and len(cap["capacity_type"]) > 0
        assert (
            isinstance(cap["commissioning_date"], str)
            and len(cap["commissioning_date"]) > 0
        )
        assert isinstance(cap["tic"], str) and len(cap["tic"]) > 0
        assert isinstance(cap["dnc"], str) and len(cap["dnc"]) > 0


def test_print_raw(station):
    print(json.dumps(station, default=asdict, indent=2))
