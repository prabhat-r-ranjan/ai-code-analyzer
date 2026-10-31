"""One-time, idempotent patch to app/excel_generator.py.

Run from the project root after backing up your code.
Only inserts the runtime sheet import and function call.
"""
from pathlib import Path

path = Path("app/excel_generator.py")
source = path.read_text(encoding="utf-8")
import_line = "from app.runtime_report_sheets import add_runtime_report_sheets"
call_line = "    add_runtime_report_sheets(wb, analysis)"
anchor_import = "from app.assessment_report_sheets import add_assessment_report_sheets"
anchor_call = "    add_assessment_report_sheets(wb, analysis)"

if anchor_import not in source or anchor_call not in source:
    raise SystemExit("Expected anchors not found; no changes made.")

if import_line not in source:
    source = source.replace(anchor_import, anchor_import + "\n" + import_line, 1)
if call_line not in source:
    source = source.replace(anchor_call, anchor_call + "\n" + call_line, 1)

compile(source, str(path), "exec")
path.write_text(source, encoding="utf-8")
print("Updated app/excel_generator.py; existing sheets preserved.")
