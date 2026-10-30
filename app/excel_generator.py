
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def create_sheet(wb, name, headers, rows):
    ws = wb.create_sheet(name)
    ws.append(headers)

    for row in rows:
        ws.append([
            str(value) if value is not None else ""
            for value in row
        ])

    header_fill = PatternFill(
        "solid", fgColor="1F4E78"
    )

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = Font(
            color="FFFFFF", bold=True
        )
        cell.alignment = Alignment(
            wrap_text=True
        )

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        max_length = max(
            len(str(cell.value or ""))
            for cell in col
        )
        ws.column_dimensions[letter].width = min(
            max(max_length + 3, 16), 65
        )

    return ws


def generate_excel(analysis):
    wb = Workbook()
    wb.remove(wb.active)

    technologies = analysis.get("technologies", [])
    apis = analysis.get("api_endpoints", [])
    databases = analysis.get("database_details", [])
    integrations = analysis.get("integration_details", [])
    downstream = analysis.get("downstream_details", [])

    # SHEET 1 — DESCRIPTION
    app_name = (
        technologies[0].get("artifact_id", "")
        if technologies else ""
    )

    description_rows = [
        ("Application Name", app_name),
        ("Repository", analysis.get("repository", "")),
        ("Branch", analysis.get("branch", "")),
        ("Business Capability", "Manual assessment required"),
        ("Application Description", "Manual assessment required"),
        ("Interfaces", f"{len(apis)} REST endpoints detected"),
        ("Database", ", ".join(
            sorted({
                str(db.get("database_type"))
                for db in databases
                if db.get("database_type")
            })
        )),
        ("Assessment Status", analysis.get("status", "")),
    ]

    create_sheet(
        wb, "Description",
        ["Attribute", "Value"],
        description_rows
    )

    # SHEET 2 — TECHNOLOGIES
    technology_rows = []

    for tech in technologies:
        for item in tech.get("classified_technology", []):
            technology_rows.append((
                item.get("category", ""),
                item.get("technology", ""),
                item.get("evidence", ""),
            ))

    create_sheet(
        wb, "Technologies",
        ["Category", "Technology", "Evidence"],
        technology_rows
    )

    # SHEET 3 — UP & DOWN STREAM
    dependency_rows = []

    for api in apis:
        dependency_rows.append((
            "Inbound",
            "REST API",
            api.get("controller", ""),
            api.get("http_method", ""),
            api.get("endpoint", ""),
            api.get("source_file", ""),
            "Declared in controller",
        ))

    for db in databases:
        target = ":".join(
            str(v) for v in (
                db.get("host"),
                db.get("port")
            ) if v is not None
        )

        dependency_rows.append((
            "Outbound",
            "Database",
            db.get("database_type", ""),
            "JDBC",
            target,
            db.get("source_file", ""),
            db.get("status", ""),
        ))

    for integration in integrations:
        dependency_rows.append((
            "To be verified",
            integration.get("name", ""),
            "",
            "",
            "",
            integration.get("source_file", ""),
            integration.get("status", ""),
        ))

    for item in downstream:
        dependency_rows.append((
            item.get("direction", ""),
            item.get("technology", ""),
            item.get("target_service", ""),
            "",
            item.get("endpoint", ""),
            item.get("source_file", ""),
            item.get("status", ""),
        ))

    create_sheet(
        wb, "Up & Down Stream",
        [
            "Direction", "Type", "Service / Controller",
            "Protocol / Method", "Endpoint / Target",
            "Source File", "Evidence / Status"
        ],
        dependency_rows
    )

    # SHEET 4 — SUMMARY
    summary_rows = [
        ("Application", app_name),
        ("Repository", analysis.get("repository", "")),
        ("POM Files", analysis.get("pom_count", 0)),
        ("Technologies", len(technology_rows)),
        ("REST Endpoints", len(apis)),
        ("Database Configurations", len(databases)),
        ("Kafka / OAuth Findings", len(integrations)),
        ("Outbound HTTP Candidates", len(downstream)),
        ("Business Flow", "Requires code and business review"),
        ("Runtime Connectivity", "Not validated"),
        ("Migration Readiness", "Assessment in progress"),
    ]

    create_sheet(
        wb, "Summary",
        ["Assessment Item", "Result"],
        summary_rows
    )

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output
