from datetime import datetime
from typing import Optional
import re
from selectolax.parser import HTMLParser  # for parsing HTML
from rer_client.models import (
    CertificateBreakdown,
    CertificateBreakdownItem,
    CertificateHistory,
    CertificateHistoryMonth,
    OrganisationCertificateGroup,
    CertificateTypeSummary,
    OrganisationContact,
    OrganisationDetail,
    OrganisationSearchResult,
    OrganisationStation,
    StationOutputSubmission,
    OrganisationStationList,
    OrganisationSummary,
    OutputDataTask,
    OutputDataTaskList,
    SchemeAccreditation,
    StationSchemeStatus,
    StationCapacity,
    StationDeclaration,
    StationDeclarationList,
    StationDeclarationTask,
    StationDeclarationTaskList,
    StationDetail,
    StationOutputSubmission,
    OrganisationOutputSubmissionGroup,
    User,
)

# region parsers


def _parse_user(html: str) -> User:
    tree = HTMLParser(html)

    h1 = tree.css_first("h1.govuk-heading-xl")
    if not h1:
        raise ValueError("Could not find user name in page")
    caption = h1.css_first("span.govuk-caption-l")
    if not caption:
        raise ValueError("Could not find user email in page")
    email = caption.text(strip=True).split(",")[-1].strip()

    # Remove caption, links, and spans to isolate the full name
    caption.decompose()
    for node in h1.css("a"):
        node.decompose()
    for node in h1.css("span"):
        node.decompose()
    full_name = h1.text(strip=True)

    # Stats
    outstanding_tasks = 0
    active_organisations = 0
    for item in tree.css(".ofgem-rer-stat__item"):
        figure = item.css_first(".ofgem-rer-stat__figure")
        description = item.css_first(".ofgem-rer-stat__description")
        if figure and description:
            count_str = figure.text(strip=True)
            label = description.text(strip=True).lower()
            try:
                count = int(count_str.replace(",", ""))
            except ValueError:
                count = 0
            if "task" in label:
                outstanding_tasks = count
            elif "organisation" in label:
                active_organisations = count

    return User(
        email=email,
        full_name=full_name,
        outstanding_tasks=outstanding_tasks,
        active_organisations=active_organisations,
    )


def _parse_user_organisations(pages: list[str]) -> list[OrganisationSummary]:
    organisations: list[OrganisationSummary] = []
    for html in pages:
        tree = HTMLParser(html)
        for row in tree.css("table tr")[1:]:
            cells = row.css("td")
            if not cells:
                continue
            org_link = cells[0].css_first("a")
            org_id = ""
            if org_link:
                href = org_link.attrs.get("href", "")
                if not href:
                    raise ValueError("Organisation link does not have href")
                org_id = href.split("/Organisations/")[-1].split("/")[0]
            organisations.append(
                OrganisationSummary(
                    organisation_id=org_id,
                    name=cells[0].text(strip=True),
                    type=cells[1].text(strip=True),
                    task_count=int(cells[2].text(strip=True) or 0),
                    status=cells[3].text(strip=True),
                    user_status=cells[4].text(strip=True),
                )
            )
    return organisations


def _parse_organisation(html: str) -> OrganisationDetail:
    tree = HTMLParser(html)

    # Parse all definition lists by position
    dls = tree.css("dl")

    def dl_to_dict(dl) -> dict[str, str]:
        result: dict[str, str] = {}
        dts = dl.css("dt")
        dds = dl.css("dd")
        for dt, dd in zip(dts, dds):
            result[dt.text(strip=True)] = dd.text(separator=" ", strip=True)
        return result

    org_dict = dl_to_dict(dls[0]) if len(dls) > 0 else {}
    contact_dict = dl_to_dict(dls[2]) if len(dls) > 2 else {}

    # Parse address separately to preserve line breaks
    # Find the dl that contains "Address" label
    address_lines = []
    for dl in dls:
        dts = dl.css("dt")
        dds = dl.css("dd")
        for dt, dd in zip(dts, dds):
            if dt.text(strip=True) == "Address":
                # Get the span containing address lines
                span = dd.css_first("span")
                if span:
                    # Iterate over child nodes to get text separated by <br/> tags
                    address_lines = [
                        child.text(strip=True)
                        for child in span.iter(include_text=True)
                        if child.text(strip=True)
                    ]
                    # Fallback: if no children, just get the text
                    if not address_lines:
                        address_text = span.text(separator=" ", strip=True)
                        address_lines = [address_text] if address_text else []
                break

    return OrganisationDetail(
        organisation_id=org_dict.get("Organisation reference", ""),
        name=org_dict.get("Organisation name", ""),
        type=org_dict.get("Organisation type", ""),
        status=org_dict.get("Account status", ""),
        address=address_lines,
        contact=OrganisationContact(
            name=contact_dict.get("Name", ""),
            email=contact_dict.get("Email address", ""),
        ),
    )


def _parse_output_data_tasks(html: str, organisation_id: str) -> OutputDataTaskList:
    tree = HTMLParser(html)
    tasks: list[OutputDataTask] = []

    for row in tree.css("table tr")[1:]:
        cells = row.css("td")
        if len(cells) < 4:
            continue
        link = cells[0].css_first("a")
        url = link.attrs.get("href", "") if link else ""
        if not url:
            raise ValueError("Task link does not have href")
        # Extract task ID from /Output/{uuid}/...
        task_id = ""
        url_parts = url.split("/")
        output_idx = next((i for i, p in enumerate(url_parts) if p == "Output"), None)
        if output_idx is not None and output_idx + 1 < len(url_parts):
            task_id = url_parts[output_idx + 1].split("?")[0]

        tasks.append(
            OutputDataTask(
                task_id=task_id,
                period=cells[0].text(strip=True),
                station_name=cells[1].text(strip=True),
                status=cells[3].text(strip=True),
                url=url,
            )
        )

    return OutputDataTaskList(organisation_id=organisation_id, tasks=tasks)


def _parse_station_declaration_tasks(
    html: str, organisation_id: str
) -> StationDeclarationTaskList:
    tree = HTMLParser(html)
    tasks: list[StationDeclarationTask] = []

    for row in tree.css("table tr")[1:]:
        cells = row.css("td")
        if len(cells) < 2:
            continue
        link = cells[0].css_first("a")
        url = link.attrs.get("href", "") if link else ""
        if not url:
            raise ValueError("Station declaration task link does not have href")
        tasks.append(
            StationDeclarationTask(
                declaration_type=cells[0].text(strip=True),
                year=cells[1].text(strip=True),
                url=url,
            )
        )

    return StationDeclarationTaskList(organisation_id=organisation_id, tasks=tasks)


def _parse_station_declarations(
    html: str, organisation_id: str
) -> StationDeclarationList:
    tree = HTMLParser(html)
    declarations: list[StationDeclaration] = []

    for row in tree.css("table tr")[1:]:
        cells = row.css("td")
        if len(cells) < 3:
            continue
        link = cells[0].css_first("a")
        url = link.attrs.get("href", "") if link else ""
        if not url:
            raise ValueError("Station declaration link does not have href")
        declarations.append(
            StationDeclaration(
                declaration_type=cells[0].text(strip=True),
                period=cells[1].text(strip=True),
                status=cells[2].text(strip=True),
                url=url,
            )
        )

    return StationDeclarationList(
        organisation_id=organisation_id, declarations=declarations
    )


def _parse_organisation_stations(
    html: str, organisation_id: str
) -> list[OrganisationStation]:
    tree = HTMLParser(html)
    stations: list[OrganisationStation] = []

    for row in tree.css("table tr")[1:]:
        cells = row.css("td")
        if len(cells) < 7:
            continue
        link = cells[1].css_first("a")
        url = link.attrs.get("href", "") if link else ""
        if not url:
            raise ValueError("Organisation station link does not have href")
        station_id = url.split("/Stations/")[-1] if url else ""
        scheme_statuses: list[StationSchemeStatus] = []
        for status_tag in cells[5].css("strong"):
            status = status_tag.text(strip=True)
            test_id = status_tag.attrs.get("data-test-id") or ""
            match = re.search(r"-(rego|ro|roofit)-status-tag$", test_id, re.IGNORECASE)
            scheme = match.group(1).upper() if match else cells[2].text(strip=True)
            if scheme == "ROOFIT":
                scheme = "ROO-FIT"
            scheme_statuses.append(StationSchemeStatus(scheme=scheme, status=status))
        stations.append(
            OrganisationStation(
                station_id=station_id,
                station_name=cells[1].text(strip=True),
                organisation_id=organisation_id,
                organisation_name=cells[0].text(strip=True),
                country=cells[3].text(strip=True),
                technology_group=cells[4].text(strip=True),
                scheme_statuses=scheme_statuses,
                last_updated=cells[6].text(strip=True),
                url=url,
            )
        )

    return stations


def _parse_station(html: str, station_id: str) -> StationDetail:
    tree = HTMLParser(html)

    # H1 spans: [org_name (caption), station_name, subtitle (caption)]
    h1 = tree.css_first("h1")
    spans = h1.css("span") if h1 else []
    captions = [s for s in spans if "govuk-caption-l" in (s.attrs.get("class") or "")]
    non_captions = [
        s for s in spans if "govuk-caption-l" not in (s.attrs.get("class") or "")
    ]
    organisation_name = captions[0].text(strip=True) if len(captions) > 0 else ""
    station_name = non_captions[0].text(strip=True) if non_captions else ""
    subtitle = captions[1].text(strip=True) if len(captions) > 1 else ""
    country = subtitle.split("|")[0].strip() if subtitle else ""

    # Merge all DL key->value pairs
    info: dict[str, str] = {}
    for dl in tree.css("dl"):
        for dt, dd in zip(dl.css("dt"), dl.css("dd")):
            key = dt.text(strip=True)
            # For address, preserve line breaks by splitting on <br/> tags
            if key == "Address":
                # Use selectolax's iter() to get all text nodes
                # The <br/> tags create separate text nodes
                address_text = dd.text(separator="\n", strip=True)
                info[key] = address_text
            else:
                info[key] = dd.text(separator=" ", strip=True)

    # Scheme accreditations table (TABLE 0)
    scheme_accreditations: list[SchemeAccreditation] = []
    tables = tree.css("table")
    if len(tables) > 0:
        for row in tables[0].css("tr")[1:]:
            cells = row.css("td")
            if len(cells) >= 5:
                scheme_accreditations.append(
                    SchemeAccreditation(
                        scheme=cells[0].text(strip=True),
                        accreditation_reference=cells[1].text(strip=True),
                        application_date=cells[2].text(strip=True),
                        effective_from=cells[3].text(strip=True),
                        status=cells[4].text(strip=True),
                    )
                )

    # Station layout capacities table (TABLE 1)
    station_capacities: list[StationCapacity] = []
    if len(tables) > 1:
        for row in tables[1].css("tr")[1:]:
            cells = row.css("td")
            if len(cells) >= 5:
                station_capacities.append(
                    StationCapacity(
                        capacity_type=cells[0].text(strip=True),
                        commissioning_date=cells[1].text(strip=True),
                        date_added=cells[2].text(strip=True),
                        tic=cells[3].text(strip=True),
                        dnc=cells[4].text(strip=True),
                    )
                )

    # Parse address lines - keep all lines as they appear in HTML
    address_lines = []
    if info.get("Address"):
        address_lines = [line.strip() for line in info["Address"].split("\n")]
        # Remove empty strings from start and end
        while address_lines and not address_lines[0]:
            address_lines.pop(0)
        while address_lines and not address_lines[-1]:
            address_lines.pop()

    return StationDetail(
        station_id=station_id,
        station_name=station_name,
        organisation_name=organisation_name,
        country=country,
        commissioning_date=info.get("Commissioning date", ""),
        total_installed_capacity=info.get("Total installed capacity (TIC)", ""),
        technology_group=info.get("Technology group", ""),
        prelim_approval=info.get("Prelim approval", ""),
        address=address_lines,
        grid_reference=info.get("Grid reference", ""),
        application_date=info.get("Application date", ""),
        declared_net_capacity=info.get("Declared net capacity", ""),
        roofit_technology=info.get("ROO-FIT technology", ""),
        rego_technology=info.get("REGO technology", ""),
        connected_to_network=info.get(
            "Connected to transmission/distribution network", ""
        ),
        will_export=info.get("Will export renewable generation", ""),
        export_connection_capacity=info.get("Export connection capacity", ""),
        station_description=info.get("Station description", ""),
        has_battery_storage=info.get("Has battery storage?", ""),
        has_standby_generator=info.get("Has standby generator", ""),
        scheme=info.get("Scheme", ""),
        rego_accredited=info.get("REGO accredited", ""),
        output_submission_frequency=info.get("Output data submission frequency", ""),
        scheme_accreditations=scheme_accreditations,
        station_capacities=station_capacities,
    )


def _parse_find_organisation(html: str) -> Optional[OrganisationSearchResult]:
    """Returns the matched organisation, or None if no match was found."""
    tree = HTMLParser(html)
    error = tree.css_first(".govuk-inset-text")
    if error:
        return None
    dl = tree.css_first("dl")
    if not dl:
        return None
    info: dict[str, str] = {}
    for dt, dd in zip(dl.css("dt"), dl.css("dd")):
        info[dt.text(strip=True)] = dd.text(strip=True)
    reference = info.get("Reference", "")
    name = info.get("Organisation", "")
    if not reference:
        return None
    return OrganisationSearchResult(reference=reference, name=name)


def _parse_certificates_overview(
    html: str, organisation_id: str
) -> OrganisationCertificateGroup:
    tree = HTMLParser(html)

    desc_el = tree.css_first(".ofgem-rer-stat__description")
    balance_period = desc_el.text(strip=True) if desc_el else ""

    summaries: list[CertificateTypeSummary] = []
    for grid_row in tree.css(".govuk-grid-row"):
        stat_el = grid_row.css_first(".ofgem-rer-stat__item")
        if not stat_el:
            continue

        h2 = stat_el.css_first("h2")
        if not h2:
            continue
        cert_type_label = h2.text(strip=True)  # e.g. "REGOs issued" or "ROCs issued"
        cert_type = "REGO" if "REGO" in cert_type_label else "ROC"

        # issued count: text of the strong figure after removing the h2
        figure_el = stat_el.css_first(".ofgem-rer-stat__figure")
        h2.decompose()
        try:
            issued = (
                int(figure_el.text(strip=True).replace(",", "")) if figure_el else 0
            )
        except ValueError:
            issued = 0

        # balance from dl/dd if present
        balance: Optional[int] = None
        dd = grid_row.css_first("dd")
        if dd:
            try:
                balance = int(dd.text(strip=True).replace(",", ""))
            except ValueError:
                balance = None

        # links
        links = grid_row.css("a.ofgem-rer-certificate-dashboard-summary__link")
        breakdown_url = links[0].attrs.get("href", "") if len(links) > 0 else ""
        history_url = links[1].attrs.get("href", "") if len(links) > 1 else ""

        if not breakdown_url:
            raise ValueError("Certificate breakdown link does not have href")
        if not history_url:
            raise ValueError("Certificate history link does not have href")

        summaries.append(
            CertificateTypeSummary(
                cert_type=cert_type,
                issued=issued,
                balance=balance,
                breakdown_url=breakdown_url,
                history_url=history_url,
            )
        )

    return OrganisationCertificateGroup(
        organisation_id=organisation_id,
        balance_period=balance_period,
        summaries=summaries,
    )


def _parse_certificate_breakdown(
    html: str, organisation_id: str, cert_type: str
) -> CertificateBreakdown:
    tree = HTMLParser(html)
    items: list[CertificateBreakdownItem] = []

    for row in tree.css("table tr")[1:]:
        cells = row.css("td")
        if len(cells) < 6:
            continue
        try:
            count = int(cells[5].text(strip=True).replace(",", ""))
        except ValueError:
            count = 0
        station_link = cells[2].css_first("a")
        if not station_link:
            raise ValueError("Certificate breakdown station row has no station link")
        station_href = station_link.attrs.get("href", "") or ""
        if "/Stations/" not in station_href:
            raise ValueError(
                "Certificate breakdown station link has an unexpected href"
            )
        station_id = station_href.split("/Stations/", 1)[1]
        if not station_id:
            raise ValueError("Certificate breakdown station link has no station ID")
        items.append(
            CertificateBreakdownItem(
                action=cells[0].text(strip=True),
                country=cells[1].text(strip=True),
                station_id=station_id,
                station=cells[2].text(strip=True),
                technology=cells[3].text(strip=True),
                output_period=cells[4].text(strip=True),
                count=count,
            )
        )

    return CertificateBreakdown(
        organisation_id=organisation_id, cert_type=cert_type, items=items
    )


def _parse_certificate_history(
    html: str, organisation_id: str, cert_type: str
) -> CertificateHistory:
    tree = HTMLParser(html)
    months: list[CertificateHistoryMonth] = []

    for row in tree.css("table tr")[1:]:
        cells = row.css("td")
        if len(cells) < 3:
            continue
        month_link = cells[0].css_first("a")
        month_url = month_link.attrs.get("href", "") if month_link else ""
        if not month_url:
            raise ValueError("Certificate history month link does not have href")
        try:
            transferred_in = int(cells[1].text(strip=True).replace(",", ""))
        except ValueError:
            transferred_in = 0
        try:
            transferred_out = int(cells[2].text(strip=True).replace(",", ""))
        except ValueError:
            transferred_out = 0
        months.append(
            CertificateHistoryMonth(
                month=cells[0].text(strip=True),
                month_url=month_url,
                transferred_in=transferred_in,
                transferred_out=transferred_out,
            )
        )

    return CertificateHistory(
        organisation_id=organisation_id, cert_type=cert_type, months=months
    )


def _parse_station_output_submissions(
    html: str, organisation_id: str
) -> OrganisationOutputSubmissionGroup:
    """Parse station output submissions from /Organisations/{organisationId}/Output.

    Args:
        html: HTML content from the output submissions page
        organisation_id: Parent organisation ID

    Returns:
        StationOutputSubmissionList containing all submissions

    Example HTML structure:
        <table>
            <tr>
                <td><a href="/Organisations/GEN/Output/{uuid}/Review">Aug 2026</a></td>
                <td>Villa Nursery</td>
                <td><span>RO<br/>REGO</span></td>
                <td>England</td>
                <td>Fuelled</td>
                <td><strong>In review</strong></td>
            </tr>
        </table>
    """
    tree = HTMLParser(html)
    submissions: list[StationOutputSubmission] = []

    for row in tree.css("table tr")[1:]:
        cells = row.css("td")
        if len(cells) < 6:
            continue

        # Extract period and URL from first cell
        link = cells[0].css_first("a")
        url = link.attrs.get("href", "") if link else ""
        if not url:
            continue

        # Extract submission ID from URL: /Organisations/{org}/Output/{uuid}/Review
        submission_id = ""
        url_parts = url.split("/")
        output_idx = next((i for i, p in enumerate(url_parts) if p == "Output"), None)
        if output_idx is not None and output_idx + 1 < len(url_parts):
            submission_id = url_parts[output_idx + 1].split("?")[0]

        # Extract schemes from third cell (may contain multiple schemes separated by <br/>)
        schemes: list[str] = []
        scheme_cell = cells[2]
        # Get text with <br/> tags converted to newlines, then split
        scheme_text = scheme_cell.text(separator="\n", strip=True)
        for scheme in scheme_text.split("\n"):
            scheme = scheme.strip()
            if scheme:
                schemes.append(scheme)

        submissions.append(
            StationOutputSubmission(
                submission_id=submission_id,
                period=cells[0].text(strip=True),
                period_month_start=datetime.strptime(
                    cells[0].text(strip=True), "%b %Y"
                ),
                station_name=cells[1].text(strip=True),
                schemes=schemes,
                country=cells[3].text(strip=True),
                technology_group=cells[4].text(strip=True),
                status=cells[5].text(strip=True),
                url=url,
            )
        )

    return OrganisationOutputSubmissionGroup(
        organisation_id=organisation_id,
        submissions=submissions,
    )


# endregion parsers
