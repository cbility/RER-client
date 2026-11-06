from __future__ import annotations

import importlib
import runpy
from typing import Any, cast
from unittest.mock import Mock

from rer_client.models import OrganisationSummary, User
from rer_scraper.service import RERScraperService

scraper_handler = importlib.import_module("rer_scraper.handler")


def make_service(
    session_cookies: dict[str, str] | None,
    retry_invoker: Mock | None = None,
) -> RERScraperService:
    smartsuite = Mock()
    smartsuite.get_operations.return_value = ["refresh_data"]
    session_auth = Mock()
    session_auth.get_cookies.return_value = session_cookies
    return RERScraperService(
        smartsuite=smartsuite,
        session_auth=session_auth,
        retry_invoker=retry_invoker or Mock(),
        function_name="scraper-function",
        ss_login_record_id="user-record",
    )


def test_handler_forwards_organisation_reference(monkeypatch):
    service = Mock()
    service.run.return_value = (204, None)

    def fake_build_service(context: Any, dry_run: bool = False) -> Mock:
        del context, dry_run
        return service

    monkeypatch.setattr(scraper_handler, "build_service", fake_build_service)

    response = scraper_handler.handler(
        {"queryStringParameters": {"organisation_reference": "GEN0191576"}}, None
    )

    assert response == {"statusCode": 204}
    service.run.assert_called_once_with(organisation_reference="GEN0191576")


def test_local_handler_runs_inline_without_aws(monkeypatch):
    for name in (
        "RER_SESSION_AUTH_API_URL",
        "RER_SESSION_AUTH_API_KEY_VALUE",
        "SMARTSUITE_ACCOUNT_ID",
        "SMARTSUITE_API_TOKEN",
    ):
        monkeypatch.setenv(name, "test")
    monkeypatch.setattr("dotenv.load_dotenv", Mock())
    service = Mock()
    service.run.return_value = (200, None)
    service_factory = Mock(return_value=service)
    monkeypatch.setattr("rer_scraper.service.RERScraperService", service_factory)
    monkeypatch.setattr("rer_scraper.smartsuite.RERSmartSuiteClient", Mock())

    assert scraper_handler.__file__
    runpy.run_path(scraper_handler.__file__, run_name="__main__")

    assert service_factory.call_args.kwargs["dry_run"] is True
    service.run.assert_called_once_with(
        schedule_retry=False, organisation_reference=None
    )


def test_targeted_refresh_retries_with_organisation_reference():
    retry_invoker = Mock()
    service = make_service(None, retry_invoker)

    status_code, result = service.run(organisation_reference="GEN0191576")

    assert (status_code, result) == (202, None)
    retry_invoker.invoke.assert_called_once_with(
        "scraper-function",
        {
            "retry_scrape": True,
            "queryStringParameters": {"organisation_reference": "GEN0191576"},
        },
    )


def test_user_update_uses_configured_login_record_id(monkeypatch):
    monkeypatch.delenv("SMARTSUITE_RECORD_ID", raising=False)
    service = make_service({"session": "cookie"})
    user = User(
        email="user@example.com",
        full_name="Test User",
        outstanding_tasks=0,
        active_organisations=0,
    )
    smartsuite_mock = cast(Any, service.smartsuite)
    smartsuite_mock.map_user.return_value = {"email": user.email}

    service.update_rer_user(user)

    smartsuite_mock.update_user.assert_called_once()
    user_record = smartsuite_mock.update_user.call_args.args[0]
    assert user_record["id"] == "user-record"


def test_targeted_refresh_skips_user_update():
    service = make_service({"session": "cookie"})
    service.client_factory = Mock(return_value=Mock())
    service.get_current_data = Mock(return_value=(Mock(), [], [], [], []))
    service.update_rer_user = Mock()
    service.update_rer_organisations = Mock(return_value={})
    service.update_rer_stations = Mock()

    status_code, _ = service.run(organisation_reference="GEN0191576")

    assert status_code == 200
    service.update_rer_user.assert_not_called()


def test_get_current_data_filters_to_requested_organisation():
    target = OrganisationSummary(
        organisation_id="GEN0191576",
        name="Target organisation",
        type="Generator",
        task_count=0,
        status="Approved",
        user_status="Active",
    )
    other = OrganisationSummary(
        organisation_id="GEN0000001",
        name="Other organisation",
        type="Generator",
        task_count=0,
        status="Approved",
        user_status="Active",
    )
    rer = Mock()
    rer.get_user_organisations.return_value = [target, other]
    rer.get_organisation_detail.return_value = Mock()
    rer.get_organisation_stations.return_value = Mock(stations=[])
    rer.get_organisation_certificates.return_value = Mock()
    rer.get_organisation_output_data.return_value = Mock()
    service = make_service({"session": "cookie"})

    _, organisations, stations, certificates, output_periods = service.get_current_data(
        rer, "GEN0191576"
    )

    assert [
        organisation.org_summary.organisation_id for organisation in organisations
    ] == ["GEN0191576"]
    assert stations == []
    assert certificates == [rer.get_organisation_certificates.return_value]
    assert output_periods == [rer.get_organisation_output_data.return_value]
    rer.get_organisation_detail.assert_called_once_with("GEN0191576")
    rer.get_organisation_stations.assert_called_once_with("GEN0191576")
