"""Parse latest HTML snapshots and generate JSON files.

This script processes all cached HTML snapshots in test/rer-html/snapshots/latest/,
parses them using the parsing functions from rer_client.parsing, and writes the
parsed JSON output to the same directory as each response.html file.

The script follows the same structure as the test files in test/rer-python/,
using the CachedRERClient to load HTML from disk.

Example output:
    test/rer-html/snapshots/latest/GEN0213742/_organisation/parsed.json
    test/rer-html/snapshots/latest/GEN0213742/_stations/parsed.json
    etc.
"""

import json
import traceback
from pathlib import Path
from typing import Any, Callable

# Add src to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rer_client.parsing import (
    _parse_certificate_breakdown,
    _parse_certificate_history,
    _parse_certificates_overview,
    _parse_find_organisation,
    _parse_organisation,
    _parse_organisation_stations,
    _parse_output_data_tasks,
    _parse_station,
    _parse_station_declaration_tasks,
    _parse_station_declarations,
    _parse_station_output_submissions,
    _parse_user,
)


def get_parser_for_directory(dir_name: str) -> tuple[Callable[..., Any], bool] | None:
    """Find the appropriate parser for a directory name.

    Args:
        dir_name: Directory name (e.g., "_organisation", "_stations")

    Returns:
        Tuple of (parser function, requires_org_id) or None if no match found
    """
    # Exact matches - parsers that don't need org_id
    if dir_name == "_user":
        return (_parse_user, False)
    elif dir_name == "_organisation":
        return (_parse_organisation, False)
    elif dir_name.startswith("_certificates_REGO_find-organisation"):
        return (_parse_find_organisation, False)

    # Individual station detail pages (e.g., _stations_469C9786-148B-4FFA-9E4B-0C30B0004AF3)
    if dir_name.startswith("_stations_") and len(dir_name) > 10:
        return (_parse_station, False)

    # Parsers that need org_id
    if dir_name == "_stations":
        return (_parse_organisation_stations, True)
    elif dir_name.startswith("_output"):
        return (_parse_output_data_tasks, True)
    elif dir_name.startswith("_tasks_output-data"):
        return (_parse_output_data_tasks, True)
    elif dir_name.startswith("_tasks_station-declarations"):
        return (_parse_station_declaration_tasks, True)
    elif dir_name.startswith("_station-declarations"):
        return (_parse_station_declarations, True)
    elif dir_name == "_certificates":
        return (_parse_certificates_overview, True)
    elif dir_name.startswith("_certificates_REGO_breakdown"):
        return (_parse_certificate_breakdown, True)
    elif dir_name.startswith("_certificates_REGO_history"):
        return (_parse_certificate_history, True)
    elif dir_name.startswith("_certificates_ROC_breakdown"):
        return (_parse_certificate_breakdown, True)
    elif dir_name.startswith("_certificates_ROC_history"):
        return (_parse_certificate_history, True)

    return None


def parse_html_file(
    html_path: Path,
    parser: Callable[..., Any],
    needs_org_id: bool,
    org_id: str = "",
    station_id: str = "",
) -> dict[str, Any] | list[dict[str, Any]]:
    """Parse an HTML file and return the result as a dictionary.

    Args:
        html_path: Path to the HTML file
        parser: Parser function to use
        needs_org_id: Whether the parser requires an organisation ID
        org_id: Organisation ID (if needed by the parser)
        station_id: Station ID (if needed by the parser)

    Returns:
        Parsed data as a dictionary
    """
    from dataclasses import asdict

    html = html_path.read_text(encoding="utf-8")

    # Call parser with appropriate arguments
    try:
        if needs_org_id and org_id:
            # Special handling for certificate breakdown/history which need cert_type
            if parser in (_parse_certificate_breakdown, _parse_certificate_history):
                # Extract cert_type from directory name
                dir_name = html_path.parent.name
                cert_type = "REGO" if "REGO" in dir_name else "ROC"
                result = parser(html, org_id, cert_type)
            else:
                result = parser(html, org_id)
        elif parser == _parse_station and station_id:
            result = parser(html, station_id)
        else:
            result = parser(html)

        # Convert to dict using the model's __dict__ or dataclass fields
        if hasattr(result, "__dataclass_fields__"):
            return asdict(result)
        elif isinstance(result, list):
            # Handle list of models
            return [
                asdict(item) if hasattr(item, "__dataclass_fields__") else item
                for item in result
            ]
        elif result is None:
            return {"result": None}
        else:
            return result.__dict__ if hasattr(result, "__dict__") else result
    except Exception as e:
        print(f"  [WARN] Error parsing {html_path.name}: {e}")
        traceback.print_exc()
        return {"error": str(e)}


def process_snapshot_directory(snapshot_dir: Path) -> int:
    """Process all HTML files in a snapshot directory.

    Args:
        snapshot_dir: Directory containing snapshot subdirectories

    Returns:
        Number of files processed
    """
    processed = 0

    # Find all subdirectories containing response.html
    for subdir in snapshot_dir.iterdir():
        if not subdir.is_dir():
            continue

        html_file = subdir / "response.html"
        if not html_file.exists():
            continue

        # Get parser for this directory
        parser_info = get_parser_for_directory(subdir.name)
        if parser_info is None:
            print(f"  [WARN] No parser found for {subdir.name}")
            continue

        parser, needs_org_id = parser_info

        # Extract organisation ID from parent directory name (e.g., GEN0213742)
        org_id = snapshot_dir.name if snapshot_dir.name.startswith("GEN") else ""

        # Extract station ID from directory name if present (e.g., _stations_469C9786-148B-4FFA-9E4B-0C30B0004AF3)
        station_id = ""
        if subdir.name.startswith("_stations_") and len(subdir.name) > 10:
            station_id = subdir.name[len("_stations_") :]

        print(f"Processing {subdir.name}...")

        # Parse HTML
        result = parse_html_file(html_file, parser, needs_org_id, org_id, station_id)

        # Write JSON
        json_path = subdir / "parsed.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"  [OK] Generated {json_path.name}")
        processed += 1

    return processed


def main():
    """Main entry point."""
    # Find the snapshots/latest directory
    script_dir = Path(__file__).parent
    snapshots_dir = script_dir / "rer-html" / "snapshots" / "latest"

    if not snapshots_dir.exists():
        print(f"Error: Snapshots directory not found: {snapshots_dir}")
        print("Run 'uv run python test/rer-html/fetch_all_snapshots.py' first.")
        sys.exit(1)

    print(f"Parsing snapshots from: {snapshots_dir}")
    print("-" * 60)

    total_processed = 0

    # Process each organisation's snapshots
    for org_dir in snapshots_dir.iterdir():
        if not org_dir.is_dir():
            continue

        print(f"\nProcessing {org_dir.name}...")
        count = process_snapshot_directory(org_dir)
        total_processed += count

    print("-" * 60)
    print(f"[OK] Successfully processed {total_processed} HTML files")


if __name__ == "__main__":
    main()
