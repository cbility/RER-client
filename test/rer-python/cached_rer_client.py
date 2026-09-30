"""Cached RER client for offline testing.

This module provides a CachedRERClient class that inherits from RERClient
and serves cached HTML responses from disk instead of making live requests
to the RER portal. Use this client in tests to avoid depending on the RER portal
being available.

The cache is organized by endpoint:
    test/rer-html/snapshots/latest/
        _user/_user/response.html
        GEN0212976/_organisation/response.html
        GEN0212976/_stations/response.html
        etc.

Usage:
    # In tests
    from test.rer-python.cached_client import CachedRERClient, FIXTURES_DIR

    rer = CachedRERClient(FIXTURES_DIR)
    orgs = rer.get_user_organisations()  # Loads from cache
"""

from pathlib import Path
from typing import Any
import requests

from rer_client import RERClient

FIXTURES_DIR = Path(__file__).parent.parent / "rer-html" / "snapshots" / "latest"
"""Default location for cached HTML fixtures."""


class CachedRERClient(RERClient):
    """
    Test client that serves cached HTML responses instead of making live requests.

    Inherits all methods from RERClient, only overriding _request and authenticate.
    Fails with a clear error if a cached response is not found.

    Example:
        >>> from test.rer-python.cached_client import CachedRERClient, FIXTURES_DIR
        >>> rer = CachedRERClient(FIXTURES_DIR)
        >>> orgs = rer.get_user_organisations()  # Loads from cache
    """

    def __init__(self, cache_dir: Path | None = None, auth_cookies: dict | None = None):
        """
        Initialize cached client.

        Args:
            cache_dir: Directory containing cached HTML files. Defaults to FIXTURES_DIR.
            auth_cookies: Ignored (kept for API compatibility with RERClient).
        """
        self.cache_dir = cache_dir or FIXTURES_DIR
        self._auth_cookies = auth_cookies  # Kept for compatibility
        # Skip authentication - just initialize the session attribute
        self.session = requests.Session()

    def authenticate(self, auth_cookies: dict, headers: dict | None = None) -> None:
        """No-op for cached client - authentication not needed."""
        pass

    def _get_cache_path(self, endpoint: str, params: dict | None = None) -> Path:
        """
        Map endpoint and params to cache file path.

        The cache uses underscore-prefixed directory names to match the fetch scripts.
        For example:
            "User" -> "_user/_user"
            "Organisations/ORG123/OrganisationReview" -> "GEN0212976/_organisation"
            "Organisations/ORG123/Stations" -> "GEN0212976/_stations"

        Args:
            endpoint: The API endpoint (e.g., "User", "Organisations/ORG123/Stations")
            params: Optional query parameters

        Returns:
            Path to the cached HTML file
        """
        # Handle pagination - include page number in path
        # Note: Output endpoint uses format _output_page-N (with dash) for all pages including page 1
        if params and "pageNumber" in params:
            page_num = params["pageNumber"]
            # Check if this is an Output endpoint
            if endpoint.endswith("/Output"):
                endpoint = f"{endpoint}_page-{page_num}"
            elif endpoint == "User" and page_num > 1:
                # User endpoint pagination: page 2+ -> "User_page2"
                endpoint = f"{endpoint}_page{page_num}"
            elif page_num > 1:
                endpoint = f"{endpoint}_page{page_num}"

        # Map endpoint to cache directory structure
        # User endpoint is special: "User" -> "_user/_user" (with optional page number)
        if endpoint == "User" or endpoint.startswith("User_"):
            if endpoint.startswith("User_"):
                # Paginated request: "User_page2" -> "_user_page-2/_user"
                page_num = endpoint.replace("User_page", "")
                return (
                    self.cache_dir
                    / f"_user_page-{page_num}"
                    / "_user"
                    / "response.html"
                )
            return self.cache_dir / "_user" / "_user" / "response.html"

        # Organisation endpoints: "Organisations/OrganisationReview/GEN123" -> "GEN123/_organisation"
        if endpoint.startswith("Organisations/"):
            parts = endpoint.split("/")
            if len(parts) >= 3:
                # Format is "Organisations/{endpoint_type}/{org_id}" or "Organisations/{org_id}/{endpoint_type}"
                # Need to detect which format based on whether parts[1] or parts[2] looks like an org ID
                if parts[1].startswith("GEN") and len(parts[1]) > 7:
                    # Format: Organisations/GEN123/EndpointType
                    org_id = parts[1]
                    endpoint_type = parts[2]
                else:
                    # Format: Organisations/EndpointType/GEN123
                    endpoint_type = parts[1]
                    org_id = parts[2]

                # Map endpoint type to cache directory name
                if endpoint_type == "OrganisationReview":
                    cache_dir = "_organisation"
                elif endpoint_type == "Stations":
                    cache_dir = "_stations"
                elif endpoint_type == "Certificates":
                    cache_dir = "_certificates"
                elif endpoint_type == "StationDeclarations":
                    cache_dir = "_station-declarations"
                elif endpoint_type == "Tasks":
                    # Tasks/OutputData or Tasks/StationDeclarations
                    if len(parts) >= 4:
                        task_type = parts[3].lower().replace("/", "-")
                        cache_dir = f"_tasks_{task_type}"
                    else:
                        cache_dir = "_tasks"
                elif endpoint_type.startswith("Output_page"):
                    # Output endpoint uses _output_page-N format (already includes page number)
                    cache_dir = f"_{endpoint_type.lower()}"
                else:
                    cache_dir = f"_{endpoint_type.lower()}"

                # Check if there's a station ID: "Organisations/GEN123/Stations/STATION-ID" or "Organisations/Stations/STATION-ID"
                if endpoint_type == "Stations" and len(parts) >= 3:
                    # Detect format: "Organisations/Stations/STATION-ID" vs "Organisations/GEN123/Stations/STATION-ID"
                    if parts[1] == "Stations":
                        # Format: Organisations/Stations/STATION-ID (station detail page)
                        station_id = parts[2]
                        # Look for station detail in any organisation directory
                        for org_dir in self.cache_dir.iterdir():
                            if org_dir.is_dir() and org_dir.name.startswith("GEN"):
                                station_path = (
                                    org_dir
                                    / f"_stations_{station_id}"
                                    / "response.html"
                                )
                                if station_path.exists():
                                    return station_path
                        # Fallback: try to find in _stations directory at root
                        return (
                            self.cache_dir / f"_stations_{station_id}" / "response.html"
                        )
                    elif len(parts) >= 4:
                        # Format: Organisations/GEN123/Stations/STATION-ID
                        station_id = parts[3]
                        return (
                            self.cache_dir
                            / org_id
                            / f"_stations_{station_id}"
                            / "response.html"
                        )

                return self.cache_dir / org_id / cache_dir / "response.html"

        # Default: just use the endpoint as-is with underscore prefix
        return self.cache_dir / f"_{endpoint.lower()}" / "response.html"

    def _request(
        self, endpoint: str, method: str = "GET", **kwargs: Any
    ) -> requests.Response:
        """
        Load cached HTML response from disk. Override _request in RERClient.

        Args:
            endpoint: The API endpoint to request
            method: HTTP method (ignored, always returns cached response)
            **kwargs: Additional request parameters (params are used for cache key)

        Returns:
            Mock Response object with cached HTML content

        Raises:
            FileNotFoundError: If cached response is not found
        """
        params = kwargs.get("params", {})
        cache_file = self._get_cache_path(endpoint, params)

        if not cache_file.exists():
            raise FileNotFoundError(
                f"Cached response not found for {endpoint!r} "
                f"(params={params}). "
                f"Expected at: {cache_file}. "
                f"Run 'uv run python test/rer-html/fetch_all_snapshots.py' to update cache."
            )

        return self._load_cache_file(cache_file)

    def _load_cache_file(self, cache_path: Path) -> requests.Response:
        """Load cached HTML file and return as mock Response."""
        response = requests.Response()
        response.status_code = 200
        response._content = cache_path.read_bytes()
        response.encoding = "utf-8"
        response.url = f"https://rer.ofgem.gov.uk/{cache_path.parent.name}"
        return response

    def get_user_organisations(
        self,
        sort_field: str | None = None,
        sort_direction: str | None = None,
    ) -> list:
        """GET /User - Returns all organisations for the authenticated user across all pages."""
        return super().get_user_organisations(sort_field, sort_direction)


def create_cached_client(
    cache_dir: Path | None = None,
    auth_cookies: dict | None = None,
) -> CachedRERClient:
    """
    Factory function to create a CachedRERClient instance.

    This is the preferred way to create a cached client for use with client_factory.

    Args:
        cache_dir: Directory containing cached HTML files. Defaults to FIXTURES_DIR.
        auth_cookies: Ignored (kept for API compatibility).

    Returns:
        CachedRERClient instance

    Example:
        >>> service = RERScraperService(
        ...     ...,
        ...     client_factory=lambda cookies: create_cached_client(),
        ... )
    """
    return CachedRERClient(cache_dir, auth_cookies)
