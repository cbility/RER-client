"""Tests for RERClient.get_organisation_certificates_breakdown() - GET /Organisations/{id}/Certificates/{type}/Breakdown"""

import json
from dataclasses import asdict
import pytest

from rer_client.models import CertificateBreakdown

ORG_ID = "GEN0212970"  # Updated to match cached data


@pytest.fixture(scope="module")
def rego_breakdown(rer):
    return rer.get_organisation_certificates_breakdown(ORG_ID, "REGO")


@pytest.fixture(scope="module")
def roc_breakdown(rer):
    return rer.get_organisation_certificates_breakdown(ORG_ID, "ROC")


def test_rego_returns_dict(rego_breakdown):
    assert isinstance(rego_breakdown, CertificateBreakdown)


def test_rego_organisation_id(rego_breakdown):
    assert rego_breakdown["organisation_id"] == ORG_ID


def test_rego_cert_type(rego_breakdown):
    assert rego_breakdown["cert_type"] == "REGO"


def test_rego_items_is_list(rego_breakdown):
    assert isinstance(rego_breakdown["items"], list)


def test_rego_items_nonempty(rego_breakdown):
    assert len(rego_breakdown["items"]) > 0


def test_rego_each_item_has_fields(rego_breakdown):
    for item in rego_breakdown["items"]:
        assert isinstance(item["action"], str)
        assert isinstance(item["country"], str)
        assert isinstance(item["station_id"], str)
        assert isinstance(item["station"], str)
        assert isinstance(item["technology"], str)
        assert isinstance(item["output_period"], str)
        assert isinstance(item["count"], int)


def test_roc_returns_dict(roc_breakdown):
    assert isinstance(roc_breakdown, CertificateBreakdown)


def test_roc_cert_type(roc_breakdown):
    assert roc_breakdown["cert_type"] == "ROC"


def test_roc_items_is_list(roc_breakdown):
    assert isinstance(roc_breakdown["items"], list)


def test_print_raw_rego(rego_breakdown):
    print(json.dumps(rego_breakdown, default=asdict, indent=2))


def test_print_raw_roc(roc_breakdown):
    print(json.dumps(roc_breakdown, default=asdict, indent=2))
