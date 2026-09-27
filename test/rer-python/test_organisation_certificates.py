"""Tests for RERClient.get_organisation_certificates() - GET /Organisations/{id}/Certificates"""

import json
from dataclasses import asdict
import pytest

from rer_client.models import OrganisationCertificates

ORG_ID = "GEN0212970"  # Updated to match cached data


def pytest_configure(config):
    pass


@pytest.fixture(scope="module")
def overview(rer):
    return rer.get_organisation_certificates(ORG_ID)


def test_returns_dict(overview):
    assert isinstance(overview, OrganisationCertificates)


def test_organisation_id(overview):
    assert overview["organisation_id"] == ORG_ID


def test_balance_period_is_string(overview):
    assert isinstance(overview["balance_period"], str)
    assert len(overview["balance_period"]) > 0


def test_summaries_is_list(overview):
    assert isinstance(overview["summaries"], list)


def test_summaries_nonempty(overview):
    assert len(overview["summaries"]) > 0


def test_each_summary_has_fields(overview):
    for s in overview["summaries"]:
        assert s["cert_type"] in ("REGO", "ROC")
        assert isinstance(s["issued"], int)
        assert isinstance(s["breakdown_url"], str) and len(s["breakdown_url"]) > 0
        assert isinstance(s["history_url"], str) and len(s["history_url"]) > 0


def test_print_raw(overview):
    print(json.dumps(overview, default=asdict, indent=2))
