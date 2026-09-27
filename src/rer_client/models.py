from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic.dataclasses import dataclass


@dataclass
class RERModel:
    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass
class RERRequest(RERModel):
    """Represents an HTTP request to the RER API.

    This model defines the structure of requests made to the RER portal.
    Used internally by RERClient for making authenticated requests.

    Example:
        method: "GET"
        path: "/organisations/GEN0213742"
        query: {"pageNumber": "1"}
        body: {}  # For POST requests
        cookies: {"session": "..."}
    """

    method: str  # HTTP method: "GET", "POST", etc.
    path: str  # API endpoint path, e.g., "/organisations/GEN0213742"
    query: dict[str, Any]  # URL query parameters
    body: dict[str, Any]  # Request body (for POST/PUT requests)
    cookies: dict[str, str]  # Authentication cookies


@dataclass
class OrganisationSummary(RERModel):
    """Summary of an organisation from the user dashboard.

    Represents organisations visible to the authenticated user on the /User
    endpoint. Each organisation includes basic details and the user's access
    status for that organisation.

    Fields:
        organisation_id: Unique organisation identifier (e.g., "GEN0213742")
        name: Organisation/company name
        type: Organisation type (e.g., "Generator Commercial", "Generator Domestic")
        task_count: Number of outstanding tasks requiring attention
        status: Account approval status (e.g., "Approved", "Pending", "Revoked")
        user_status: User's access status with this organisation. Common values:
            - "Active": User has active access to the organisation
            - "Suspended": User access is suspended or removed

    Example:
        organisation_id: "GEN0213742"
        name: "GLENSKINNO BIOFUELS LTD"
        type: "Generator Commercial"
        task_count: 685
        status: "Approved"
        user_status: "Active"
    """

    organisation_id: str  # Unique organisation identifier, e.g., "GEN0213742"
    name: str  # Organisation/company name
    type: str  # Organisation type, e.g., "Generator Commercial", "Generator Domestic"
    task_count: int  # Number of outstanding tasks for this organisation
    status: str  # Account status, e.g., " Approved", "Pending"
    user_status: (
        str  # User's access status with this organisation (e.g., "Active", "Suspended")
    )


@dataclass
class User(RERModel):
    """User dashboard information from /User endpoint.

    Example:
        email: "technical@yourenergysource.co.uk"
        full_name: "Toby White"
        outstanding_tasks: 685
        active_organisations: 58
    """

    email: str  # User's email address
    full_name: str  # User's full display name
    outstanding_tasks: int  # Total number of tasks requiring attention
    active_organisations: int  # Number of organisations the user has access to


@dataclass
class OrganisationContact(RERModel):
    """Primary contact information for an organisation.

    Example:
        name: "Unknown user"
        email: "catherine@asaw.co.uk"
    """

    name: str  # Contact person's name (may be "Unknown user" if not set)
    email: str  # Contact email address


@dataclass
class OrganisationDetail(RERModel):
    """Detailed information about an organisation from /Organisations/{id}.

    Represents the complete organisation overview page, including address,
    contact details, and company registration information.

    Fields:
        organisation_id: Unique identifier (e.g., "GEN0213742")
        name: Organisation/company name
        type: Organisation type (e.g., "Generator Commercial", "Generator Domestic")
        status: Account approval status (e.g., "APPROVED", "Pending", "Revoked")
        address: Registered address as a list of lines (line 1, [line 2,] city, [region,] postcode, country)
        contact: Primary contact person's name and email

    Example:
        organisation_id: "GEN0213742"
        name: "GLENSKINNO BIOFUELS LTD"
        type: "Generator Commercial"
        status: "APPROVED"
        address: [
            "2 Stewart Street",
            "Milngavie",
            "GLASGOW",
            "G62 6BW",
            "Scotland"
        ]
        contact: OrganisationContact(
            name="Catherine Smith",
            email="catherine@asaw.co.uk"
        )
    """

    organisation_id: str  # Unique identifier, e.g., "GEN0213742"
    name: str  # Organisation/company name
    type: str  # Organisation type, e.g., "Generator Commercial"
    status: str  # Account status, e.g., "APPROVED"
    address: list[str]  # Address lines (street, city, postcode, country)
    contact: OrganisationContact  # Primary contact information


@dataclass
class OutputDataTask(RERModel):
    """Single output data submission task.

    Example:
        task_id: "19e630d6-2383-414a-a384-499aedce47c7"
        period: "Aug 2026"
        station_name: "Glenskinno CHP"
        status: "Draft"
        url: "/Organisations/GEN0213742/Output/19e630d6-2383-414a-a384-499aedce47c7/Edit"
    """

    task_id: str  # UUID of the task, e.g., "19e630d6-2383-414a-a384-499aedce47c7"
    period: str  # Reporting period in "Mon YYYY" format, e.g., "Aug 2026"
    station_name: str  # Name of the station for this task
    status: str  # Task status, e.g., "Draft", "Submitted", "Approved"
    url: str  # Relative URL to edit/view this task


@dataclass
class OutputDataTaskList(RERModel):
    """Collection of output data tasks for an organisation.

    Example:
        organisation_id: "GEN0213742"
        tasks: [OutputDataTask, ...]
    """

    organisation_id: str  # Parent organisation ID
    tasks: list[OutputDataTask]  # List of output data submission tasks


@dataclass
class StationDeclarationTask(RERModel):
    """Pending station declaration task.

    Example:
        declaration_type: "Information (1)"
        year: "2025/2026"
        url: "/Organisations/GEN0213742/AcceptPendingDeclaration/Pending/1/2025-04-01/2026-03-31"
    """

    declaration_type: (
        str  # Type of declaration, e.g., "Information (1)", "ROS Permitted Ways"
    )
    year: str  # Reporting year in "YYYY/YYYY" format
    url: str  # Relative URL to complete this declaration


@dataclass
class StationDeclarationTaskList(RERModel):
    """Collection of station declaration tasks for an organisation."""

    organisation_id: str  # Parent organisation ID
    tasks: list[StationDeclarationTask]  # List of pending declaration tasks


@dataclass
class StationDeclaration(RERModel):
    """Station declaration record with status.

    Example:
        declaration_type: "Information (1)"
        period: "2025/2026"
        status: "signed"  # or "pending"
        url: "/Organisations/GEN0213742/AcceptPendingDeclaration/Pending/1/2025-04-01/2026-03-31"
    """

    declaration_type: (
        str  # Type of declaration, e.g., "Information (1)", "ROS Permitted Ways"
    )
    period: str  # Declaration period in "YYYY/YYYY" format
    status: str  # Declaration status: "pending", "signed", etc.
    url: str  # Relative URL to view/manage this declaration


@dataclass
class StationDeclarationList(RERModel):
    """Collection of station declarations for an organisation."""

    organisation_id: str  # Parent organisation ID
    declarations: list[StationDeclaration]  # List of station declarations


@dataclass
class StationSchemeStatus(RERModel):
    """Scheme accreditation status for a station.

    Example:
        scheme: "REGO"  # or "RO", "ROO-FIT"
        status: "Approved"
    """

    scheme: str  # Scheme name: "RO", "REGO" or "ROO-FIT"
    status: str  # Accreditation status, e.g., "Approved", "Pending"


@dataclass
class OrganisationStation(RERModel):
    """Station summary from organisation stations list.

    Example:
        station_id: "469C9786-148B-4FFA-9E4B-0C30B0004AF3"
        station_name: "Glenskinno CHP"
        organisation_id: "GEN0213742"
        organisation_name: "GLENSKINNO BIOFUELS LTD"
        country: "Scotland"
        technology_group: "Fuelled"
        scheme_statuses: [StationSchemeStatus(...)]
        last_updated: "08/11/2017"
        url: "/Organisations/Stations/469C9786-148B-4FFA-9E4B-0C30B0004AF3"
    """

    station_id: str  # UUID of the station
    station_name: str  # Display name of the station
    organisation_id: str  # Parent organisation ID
    organisation_name: str  # Parent organisation name
    country: str  # Country location, e.g., "Scotland", "England"
    technology_group: str  # Technology classification, e.g., "Fuelled", "Wind", "Solar"
    scheme_statuses: list[StationSchemeStatus]  # Status for each accreditation scheme
    last_updated: str  # Date of last update in "DD/MM/YYYY" format
    url: str  # Relative URL to station details page


@dataclass
class OrganisationStationList(RERModel):
    """Collection of stations for an organisation."""

    organisation_id: str  # Parent organisation ID
    stations: list[OrganisationStation]  # List of stations for the organisation


@dataclass
class SchemeAccreditation(RERModel):
    """Individual scheme accreditation for a station.

    Example:
        scheme: "RO"
        accreditation_reference: "R00028SXSC"
        application_date: "05/09/2016"
        effective_from: "05/09/2016"
        status: "Approved"
    """

    scheme: str  # Scheme name: "RO", "REGO", etc.
    accreditation_reference: str  # Unique reference, e.g., "R00028SXSC", "G01130BWSC"
    application_date: str  # Date application submitted (DD/MM/YYYY)
    effective_from: str  # Date accreditation became effective (DD/MM/YYYY)
    status: str  # Accreditation status, e.g., "Approved"


@dataclass
class StationCapacity(RERModel):
    """Station capacity measurement record.

    Example:
        capacity_type: "Original"
        commissioning_date: "30/06/2016"
        date_added: "01/09/2016"
        tic: "49 kW"  # Total Installed Capacity
        dnc: "48.638 kW"  # Declared Net Capacity
    """

    capacity_type: str  # Type of capacity record, e.g., "Original", "Updated"
    commissioning_date: str  # Date station was commissioned (DD/MM/YYYY)
    date_added: str  # Date this record was added (DD/MM/YYYY)
    tic: str  # Total Installed Capacity with units, e.g., "49 kW"
    dnc: str  # Declared Net Capacity with units, e.g., "48.638 kW"


@dataclass
class StationDetail(RERModel):
    """Complete station details from /Organisations/Stations/{stationId}.

    Example:
        station_id: "469C9786-148B-4FFA-9E4B-0C30B0004AF3"
        station_name: "Glenskinno CHP"
        organisation_name: "GLENSKINNO BIOFUELS LTD"
        country: "Scotland"
        commissioning_date: "30/06/2016"
        total_installed_capacity: "49 kW"
        technology_group: "Fuelled"
        prelim_approval: ""
        address: " Glenskinno Farm Montrose DD10 9LG Scotland "
        grid_reference: "NO682604"
        application_date: "05/09/2016"
        declared_net_capacity: "48.638 kW"
        roofit_technology: ""
        rego_technology: "Biomass"
        connected_to_network: ""
        will_export: ""
        export_connection_capacity: "0 kW"
        station_description: "1no ESPE CHip50 biomass CHP unit..."
        has_battery_storage: ""
        has_standby_generator: "No"
        scheme: "RO"
        rego_accredited: "Yes"
        output_submission_frequency: "Monthly"
    """

    station_id: str  # UUID of the station
    station_name: str  # Display name of the station
    organisation_name: str  # Parent organisation name
    country: str  # Country location
    commissioning_date: str  # Date station was commissioned (DD/MM/YYYY)
    total_installed_capacity: str  # Total capacity with units, e.g., "49 kW"
    technology_group: str  # Technology classification
    prelim_approval: str  # Preliminary approval status (may be empty)
    address: str  # Full station address
    grid_reference: str  # UK grid reference, e.g., "NO682604"
    application_date: str  # Date application submitted (DD/MM/YYYY)
    declared_net_capacity: str  # Net capacity with units, e.g., "48.638 kW"
    roofit_technology: str  # ROO-FIT technology type (may be empty)
    rego_technology: str  # REGO technology fuel type, e.g., "Biomass"
    connected_to_network: str  # Network connection status (may be empty)
    will_export: str  # Export intention (may be empty)
    export_connection_capacity: str  # Export capacity with units
    station_description: str  # Detailed technical description
    has_battery_storage: str  # Battery storage indicator (may be empty)
    has_standby_generator: str  # Standby generator indicator, e.g., "No"
    scheme: str  # Primary scheme, e.g., "RO"
    rego_accredited: str  # REGO accreditation status, e.g., "Yes"
    output_submission_frequency: str  # Reporting frequency, e.g., "Monthly"
    scheme_accreditations: list[SchemeAccreditation]  # All scheme accreditations
    station_capacities: list[StationCapacity]  # All capacity records


@dataclass
class OrganisationSearchResult(RERModel):
    """Result from organisation search by reference.

    Example:
        reference: "GEN0213742"
        name: "GLENSKINNO BIOFUELS LTD"
    """

    reference: str  # Organisation reference/ID
    name: str  # Organisation name


@dataclass
class CertificateTypeSummary(RERModel):
    """Summary of certificates by type for an organisation.

    Example:
        cert_type: "REGO"  # or "ROC"
        issued: 0
        balance: 0  # or None if not applicable
        breakdown_url: "/Organisations/GEN0213742/Certificates/REGO/Breakdown"
        history_url: "/Organisations/GEN0213742/Certificates/REGO/History"
    """

    cert_type: str  # Certificate type: "ROC", "REGO"
    issued: int  # Number of certificates issued
    balance: int | None  # Current balance (may be None for some types)
    breakdown_url: str  # URL to view breakdown by period/station
    history_url: str  # URL to view transfer history


@dataclass
class OrganisationCertificateGroup(RERModel):
    """Overview of all certificates for an organisation.

    Example:
        organisation_id: "GEN0213742"
        balance_period: "Balance of issued certificates from 2025 to 2027"
        summaries: [CertificateTypeSummary(...), ...]
    """

    organisation_id: str  # Parent organisation ID
    balance_period: str  # Description of the balance period
    summaries: list[CertificateTypeSummary]  # Summary for each certificate type


@dataclass
class CertificateBreakdownItem(RERModel):
    """Individual certificate entry in a breakdown view.

    Example:
        action: "Issued"  # or "Transferred"
        country: "Scotland"
        station_id: "469C9786-148B-4FFA-9E4B-0C30B0004AF3"
        station: "Glenskinno CHP"
        technology: "Biomass"
        output_period: "Aug 2025"
        count: 10
    """

    action: str  # Certificate action: "Issued", "Transferred", etc.
    country: str  # Country where generated
    station_id: str  # Station UUID from the station details link
    station: str  # Station name
    technology: str  # Technology/fuel type
    output_period: str  # Period in "Mon YYYY" format
    count: int  # Number of certificates


@dataclass
class CertificateBreakdown(RERModel):
    """Detailed breakdown of certificates by period/station.

    Example:
        organisation_id: "GEN0213742"
        cert_type: "REGO"
        items: [CertificateBreakdownItem(...), ...]
    """

    organisation_id: str  # Parent organisation ID
    cert_type: str  # Certificate type: "ROC", "REGO"
    items: list[CertificateBreakdownItem]  # Individual certificate records


@dataclass
class CertificateHistoryMonth(RERModel):
    """Monthly certificate transfer history.

    Example:
        month: "Aug 2025"
        month_url: "/Organisations/GEN0213742/Certificates/REGO/History/2025-08"
        transferred_in: 50
        transferred_out: 30
    """

    month: str  # Month in "Mon YYYY" format
    month_url: str  # URL to view detailed history for this month
    transferred_in: int  # Certificates transferred into organisation
    transferred_out: int  # Certificates transferred out of organisation


@dataclass
class CertificateHistory(RERModel):
    """Certificate transfer history for an organisation.

    Example:
        organisation_id: "GEN0213742"
        cert_type: "REGO"
        months: [CertificateHistoryMonth(...), ...]
    """

    organisation_id: str  # Parent organisation ID
    cert_type: str  # Certificate type: "ROC", "REGO"
    months: list[CertificateHistoryMonth]  # Monthly history records


@dataclass
class StationOutputSubmission(RERModel):
    """Station output data submission record.

    Represents a single output data submission for a station.
    Retrieved from /Organisations/{organisationId}/Output endpoint.

    Fields:
        submission_id: UUID of the submission (e.g., "2b916360-8484-4bf8-a7ea-d1902ff29ade")
        period: Reporting period in "Mon YYYY" format (e.g., "Aug 2026")
        period_month_start: Start date of the reporting month as datetime
        station_name: Name of the station
        schemes: List of schemes (e.g., ["RO", "REGO"], ["REGO", "ROO-FIT"], or ["REGO"])
                   Common values: "RO" (Renewables Obligation), "REGO" (Renewables Energy Guarantees of Origin),
                   "ROO-FIT" (Renewables Obligation Order - Feed-in Tariff)
        country: Country location (e.g., "England", "Scotland")
        technology_group: Technology classification (e.g., "Fuelled", "Wind")
        status: Submission status (e.g., "In review", "Pending", "Approved", "Draft")
        url: Relative URL to view/review this submission

    Example:
        submission_id: "2b916360-8484-4bf8-a7ea-d1902ff29ade"
        period: "Aug 2026"
        station_name: "Villa Nursery"
        schemes: ["RO", "REGO"]
        country: "England"
        technology_group: "Fuelled"
        status: "In review"
        url: "/Organisations/GEN0208381/Output/2b916360-8484-4bf8-a7ea-d1902ff29ade/Review"
    """

    submission_id: str  # UUID of the submission
    period: str  # Reporting period in "Mon YYYY" format
    period_month_start: datetime  # Start date of the reporting month as datetime
    station_name: str  # Name of the station
    schemes: list[str]  # List of schemes: "RO", "REGO", etc.
    country: str  # Country location
    technology_group: str  # Technology classification
    status: str  # Submission status
    url: str  # Relative URL to view/review submission


@dataclass
class OrganisationOutputSubmissionGroup(RERModel):
    """Collection of station output submissions for an organisation.

    Example:
        organisation_id: "GEN0208381"
        submissions: [StationOutputSubmission, ...]
    """

    organisation_id: str  # Parent organisation ID
    submissions: list[StationOutputSubmission]  # List of output submissions
