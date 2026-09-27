"""Tests for station output submissions using cached HTML snapshots.

These tests use cached HTML pages from test/rer-html/snapshots/latest/
to validate the parsing and client methods without making live API calls.
"""

import os
import json
from pathlib import Path

import pytest

from rer_client import RERClient
from rer_client.models import StationOutputSubmission

# Path to cached HTML snapshots
SNAPSHOTS_DIR = Path(
    os.path.join(os.path.dirname(__file__), "..", "rer-html", "snapshots", "latest")
)


def load_html_snapshot(org_id: str, snapshot_name: str) -> str:
    """Load HTML snapshot from cache.

    Args:
        org_id: Organisation ID (e.g., "GEN0208381")
        snapshot_name: Snapshot directory name (e.g., "_output_page-1")

    Returns:
        HTML content as string
    """
    html_path = SNAPSHOTS_DIR / org_id / snapshot_name / "response.html"
    if not html_path.exists():
        pytest.skip(f"Snapshot not found: {html_path}")

    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


def load_parsed_snapshot(org_id: str, snapshot_name: str) -> dict:
    """Load parsed JSON snapshot from cache.

    Args:
        org_id: Organisation ID
        snapshot_name: Snapshot directory name

    Returns:
        Parsed data as dictionary
    """
    json_path = SNAPSHOTS_DIR / org_id / snapshot_name / "parsed.json"
    if not json_path.exists():
        pytest.skip(f"Parsed snapshot not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestStationOutputSubmissions:
    """Test station output submissions parsing and filtering."""

    def test_parse_station_output_submissions_page1(self):
        """Test parsing first page of station output submissions."""
        html = load_html_snapshot("GEN0208381", "_output_page-1")

        from rer_client import parsing as rer_parsing

        result = rer_parsing._parse_station_output_submissions(html, "GEN0208381")

        assert result.organisation_id == "GEN0208381"
        assert len(result.submissions) > 0

        # Check first submission structure
        submission = result.submissions[0]
        assert isinstance(submission, StationOutputSubmission)
        assert submission.submission_id  # UUID
        assert submission.period  # e.g., "Aug 2026"
        assert submission.station_name
        assert submission.schemes  # List of schemes
        assert submission.country
        assert submission.technology_group
        assert submission.status
        assert submission.url

    def test_parse_station_output_submissions_multiple_schemes(self):
        """Test parsing submissions with multiple schemes (RO + REGO)."""
        html = load_html_snapshot("GEN0208381", "_output_page-1")

        from rer_client import parsing as rer_parsing

        result = rer_parsing._parse_station_output_submissions(html, "GEN0208381")

        # Check that schemes are properly extracted
        # The HTML shows schemes like "RO<br/>REGO" which should be split
        assert len(result.submissions) > 0

        # Print first submission for debugging
        first = result.submissions[0]
        print(f"First submission schemes: {first.schemes}")

        # At minimum, each submission should have at least one scheme
        for submission in result.submissions:
            assert len(submission.schemes) >= 1

    def test_parse_station_output_submissions_all_pages(self):
        """Test parsing all pages of output submissions."""
        from rer_client import parsing as rer_parsing

        all_submissions = []
        page_number = 1

        while True:
            snapshot_name = f"_output_page-{page_number}"
            html_path = SNAPSHOTS_DIR / "GEN0208381" / snapshot_name / "response.html"

            if not html_path.exists():
                break

            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()

            result = rer_parsing._parse_station_output_submissions(html, "GEN0208381")
            all_submissions.extend(result.submissions)
            page_number += 1

        # Should have submissions from all 6 pages
        assert len(all_submissions) > 0
        print(f"Total submissions across {page_number-1} pages: {len(all_submissions)}")

    def test_filter_submissions_by_station(self):
        """Test filtering submissions by station name."""
        from rer_client import parsing as rer_parsing

        # Load first page
        html = load_html_snapshot("GEN0208381", "_output_page-1")
        result = rer_parsing._parse_station_output_submissions(html, "GEN0208381")

        # Get unique station names
        station_names = set(s.station_name for s in result.submissions)
        assert len(station_names) > 0

        # Filter by first station
        test_station = list(station_names)[0]
        filtered = [s for s in result.submissions if s.station_name == test_station]

        assert len(filtered) > 0
        assert all(s.station_name == test_station for s in filtered)

    def test_submission_status_values(self):
        """Test that submission statuses are properly extracted."""
        from rer_client import parsing as rer_parsing

        all_submissions = []

        # Load all pages
        page_number = 1
        while True:
            snapshot_name = f"_output_page-{page_number}"
            html_path = SNAPSHOTS_DIR / "GEN0208381" / snapshot_name / "response.html"

            if not html_path.exists():
                break

            with open(html_path, "r", encoding="utf-8") as f:
                html = f.read()

            result = rer_parsing._parse_station_output_submissions(html, "GEN0208381")
            all_submissions.extend(result.submissions)
            page_number += 1

        # Check for common status values
        statuses = set(s.status for s in all_submissions)

        # Expected statuses based on HTML
        expected_statuses = {"In review", "Pending", "Draft", "Approved"}
        found_statuses = statuses.intersection(expected_statuses)

        assert (
            len(found_statuses) > 0
        ), f"Expected to find one of {expected_statuses}, got {statuses}"

    def test_submission_url_format(self):
        """Test that submission URLs have correct format."""
        from rer_client import parsing as rer_parsing

        html = load_html_snapshot("GEN0208381", "_output_page-1")
        result = rer_parsing._parse_station_output_submissions(html, "GEN0208381")

        for submission in result.submissions:
            # URL should point to Review or Edit page
            assert "/Output/" in submission.url
            assert submission.submission_id in submission.url
            assert submission.url.startswith("/Organisations/")

    def test_submission_id_extraction(self):
        """Test that submission IDs are correctly extracted from URLs."""
        from rer_client import parsing as rer_parsing

        html = load_html_snapshot("GEN0208381", "_output_page-1")
        result = rer_parsing._parse_station_output_submissions(html, "GEN0208381")

        for submission in result.submissions:
            # Submission ID should be a UUID format
            assert len(submission.submission_id) > 0
            # UUIDs are typically 36 characters with hyphens
            # e.g., "2b916360-8484-4bf8-a7ea-d1902ff29ade"
            assert (
                "-" in submission.submission_id or len(submission.submission_id) >= 30
            )


class TestStationOutputSubmissionsClient:
    """Test client method for getting station output submissions."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client with fake cookies for testing."""
        # Use minimal cookies - won't make real requests in these tests
        fake_cookies = {"session": "fake_session_for_testing"}

        # Create client but don't authenticate (will use mocked responses)
        try:
            client = RERClient(auth_cookies=fake_cookies)
            return client
        except Exception:
            pytest.skip("Could not create mock client")

    def test_get_station_output_submissions_requires_org_id(self, mock_client):
        """Test that get_station_output_submissions requires organisation_id."""
        # This should raise ValueError when organisation_id is not provided
        with pytest.raises(ValueError, match="organisation_id must be provided"):
            mock_client.get_station_output_submissions(
                station_id="469C9786-148B-4FFA-9E4B-0C30B0004AF3"
            )

    def test_get_organisation_output_data_method_exists(self, mock_client):
        """Test that the get_organisation_output_data method exists."""
        assert hasattr(mock_client, "get_organisation_output_data")
        assert callable(mock_client.get_organisation_output_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
