"""Fetch and save HTML for all RER endpoints across all organisations.

This script:
1. Authenticates with RER using saved cookies
2. Fetches the user dashboard to get all organisation IDs
3. For each organisation, fetches all available endpoints
4. Saves raw HTML for each request
5. Organises output in a structured directory

Output structure:
    snapshots/
        {organisation_id}/
            {endpoint}/
                response.html
"""

import os
import logging
from datetime import datetime
from pathlib import Path

from _auth import get_client

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# Output directory
OUTPUT_BASE = Path(os.path.join(os.path.dirname(__file__), "snapshots"))
OUTPUT_BASE.mkdir(exist_ok=True)

# Create timestamp for this run
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_DIR = OUTPUT_BASE / TIMESTAMP
RUN_DIR.mkdir(exist_ok=True)


def save_snapshot(org_id: str, endpoint: str, html: str):
    """Save HTML snapshot for an endpoint."""
    org_dir = RUN_DIR / org_id
    endpoint_dir = org_dir / endpoint.replace("/", "_")
    endpoint_dir.mkdir(parents=True, exist_ok=True)

    # Save HTML
    html_path = endpoint_dir / "response.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    log.info(f"  ✓ {endpoint}")


def main():
    log.info("=" * 80)
    log.info("RER Data Snapshot Tool")
    log.info("=" * 80)
    log.info(f"Output directory: {RUN_DIR}")
    log.info("")

    # Get authenticated client
    log.info("Authenticating with RER...")
    try:
        client = get_client()
        user = client.get_user()
        log.info(f"Authenticated as: {user.full_name} ({user.email})")
    except FileNotFoundError as e:
        log.error(f"✗ Authentication failed: {e}")
        log.error("")
        log.error(
            "Run 'uv run python test/bootstrap_rer_cookies.py' to regenerate cookies."
        )
        raise SystemExit(1)
    except ValueError as e:
        log.error(f"✗ Authentication failed: {e}")
        log.error("")
        log.error("Your RER cookies may be expired or invalid.")
        log.error(
            "Run 'uv run python test/bootstrap_rer_cookies.py' to regenerate cookies."
        )
        raise SystemExit(1)
    except Exception as e:
        log.error(f"✗ Unexpected authentication error: {e}")
        log.error("")
        log.error("Check that rer_cookies.json exists and is valid.")
        raise SystemExit(1)

    log.info("")

    # Get all organisations
    log.info("Fetching organisation list...")
    organisations = client.get_user_org_summary()
    log.info(f"Found {len(organisations)} organisation(s)")
    log.info("")

    # Save user dashboard
    log.info("Saving user dashboard...")
    user_response = client._request("User")
    save_snapshot("_user", "/user", user_response.text)
    log.info("")

    # Process each organisation
    for org in organisations:
        org_id = org.organisation_id
        org_name = org.name
        log.info(f"Processing: {org_name} ({org_id})")

        try:
            # 1. Organisation details
            try:
                log.info("  Fetching organisation details...")
                response = client._request(f"Organisations/OrganisationReview/{org_id}")
                save_snapshot(org_id, "/organisation", response.text)
            except Exception as e:
                log.error(f"  ✗ Organisation details: {e}")

            # 2. Stations list
            try:
                log.info("  Fetching stations...")
                response = client._request(f"Organisations/{org_id}/Stations")
                save_snapshot(org_id, "/stations", response.text)
            except Exception as e:
                log.error(f"  ✗ Stations: {e}")

            # 3. Station declarations
            try:
                log.info("  Fetching station declarations...")
                response = client._request(
                    f"Organisations/{org_id}/StationDeclarations"
                )
                save_snapshot(
                    org_id,
                    "/station-declarations",
                    response.text,
                )
            except Exception as e:
                log.error(f"  ✗ Station declarations: {e}")

            # 4. Certificates overview
            try:
                log.info("  Fetching certificates overview...")
                response = client._request(f"Organisations/{org_id}/Certificates")
                save_snapshot(org_id, "/certificates", response.text)
            except Exception as e:
                log.error(f"  ✗ Certificates overview: {e}")

            # 5. Output data tasks (paginated)
            try:
                log.info("  Fetching output data tasks...")
                page_number = 1
                while True:
                    response = client._request(
                        f"Organisations/{org_id}/Tasks/OutputData",
                        params={"pageNumber": page_number},
                    )
                    parsed = client.get_organisation_output_data_tasks(
                        org_id, page_number=page_number
                    )
                    if not parsed.tasks:
                        break
                    save_snapshot(
                        org_id,
                        f"/tasks/output-data/page-{page_number}",
                        response.text,
                    )
                    page_number += 1
            except Exception as e:
                log.error(f"  ✗ Output data tasks: {e}")

            # 5b. Output submissions, all periods/statuses (paginated)
            try:
                log.info("  Fetching output submissions...")
                page_number = 1
                while True:
                    response = client._request(
                        f"Organisations/{org_id}/Output",
                        params={
                            "sortField": "Period",
                            "sortDirection": "Desc",
                            "pageNumber": page_number,
                        },
                    )
                    save_snapshot(
                        org_id,
                        f"/output/page-{page_number}",
                        response.text,
                    )
                    page_number += 1
            except Exception as e:
                log.error(f"  ✗ Output submissions: {e}")

            # 6. Station declaration tasks
            try:
                log.info("  Fetching station declaration tasks...")
                response = client._request(
                    f"Organisations/{org_id}/Tasks/StationDeclarations"
                )
                save_snapshot(
                    org_id,
                    "/tasks/station-declarations",
                    response.text,
                )
            except Exception as e:
                log.error(f"  ✗ Station declaration tasks: {e}")

            # 7. Certificate breakdown (need to get cert types first)
            try:
                log.info("  Fetching certificates for breakdown...")
                certs_overview = client.get_organisation_certificates(org_id)

                # Get unique certificate types
                cert_types = set()
                if hasattr(certs_overview, "summaries") and certs_overview.summaries:
                    for summary in certs_overview.summaries:
                        if hasattr(summary, "cert_type"):
                            cert_types.add(summary.cert_type)

                # Fetch breakdown for each cert type
                for cert_type in cert_types:
                    try:
                        log.info(f"    Fetching {cert_type} breakdown...")
                        response = client._request(
                            f"Organisations/{org_id}/Certificates/{cert_type}/Breakdown"
                        )
                        save_snapshot(
                            org_id,
                            f"/certificates/{cert_type}/breakdown",
                            response.text,
                        )
                    except Exception as e:
                        log.error(f"    ✗ {cert_type} breakdown: {e}")
            except Exception as e:
                log.error(f"  ✗ Certificate breakdown: {e}")

            # 8. Certificate history (need to get cert types first)
            try:
                log.info("  Fetching certificates for history...")
                certs_overview = client.get_organisation_certificates(org_id)

                # Get unique certificate types
                cert_types = set()
                if hasattr(certs_overview, "summaries") and certs_overview.summaries:
                    for summary in certs_overview.summaries:
                        if hasattr(summary, "cert_type"):
                            cert_types.add(summary.cert_type)

                # Fetch history for each cert type
                for cert_type in cert_types:
                    try:
                        log.info(f"    Fetching {cert_type} history...")
                        response = client._request(
                            f"Organisations/{org_id}/Certificates/{cert_type}/History"
                        )
                        save_snapshot(
                            org_id,
                            f"/certificates/{cert_type}/history",
                            response.text,
                        )
                    except Exception as e:
                        log.error(f"    ✗ {cert_type} history: {e}")
            except Exception as e:
                log.error(f"  ✗ Certificate history: {e}")

            # 8b. Find Organisation endpoint (for certificate transfers)
            # This endpoint is used to search for a recipient organisation when transferring certificates
            try:
                log.info(
                    "  Fetching FindOrganisation endpoint (certificate transfer)..."
                )
                # Use a known organisation reference to test the endpoint
                test_reference = "GEN0212970"  # Use an organisation we know exists
                response = client._request(
                    f"Organisations/{org_id}/Certificates/REGO/FindOrganisation"
                )
                # This is a POST endpoint that requires form data, but we can cache the GET response
                # which shows the form. The actual search happens via POST.
                save_snapshot(
                    org_id,
                    "/certificates/REGO/find-organisation",
                    response.text,
                )
            except Exception as e:
                log.error(f"  ✗ FindOrganisation: {e}")

            # 9. Individual station details (from stations list)
            try:
                stations = client.get_organisation_stations(org_id)
                for station in stations[
                    :5
                ]:  # Limit to first 5 stations to avoid too many requests
                    station_id = station.station_id
                    log.info(
                        f"    Fetching station: {station.station_name} ({station_id})"
                    )
                    response = client._request(f"Organisations/Stations/{station_id}")
                    save_snapshot(
                        org_id,
                        f"/stations/{station_id}",
                        response.text,
                    )
            except Exception as e:
                log.error(f"  ✗ Station details: {e}")

            log.info("")

        except Exception as e:
            log.error(f"✗ Error processing organisation {org_id}: {e}")
            log.info("")

    log.info("=" * 80)
    log.info(f"Snapshot complete! Files saved to: {RUN_DIR}")
    log.info("=" * 80)


if __name__ == "__main__":
    main()
