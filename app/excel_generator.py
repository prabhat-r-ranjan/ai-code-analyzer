
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def generate_excel(analysis: dict) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Technologies"

    ws.append(["Category", "Technology", "Evidence"])

    for module in analysis.get("technologies", []):
        for item in module.get("classified_technology", []):
            ws.append([
                item.get("category", ""),
                item.get("technology", ""),
                item.get("evidence", ""),
            ])

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="70AD47"
    )

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")

    for col, width in enumerate([28, 35, 75], start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output
