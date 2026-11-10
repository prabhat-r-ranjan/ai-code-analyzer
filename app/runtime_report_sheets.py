"""Optional runtime Excel sheets. Original 8 source sheets are unchanged."""
from __future__ import annotations
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def _safe(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def _sheet(wb, title, headers, rows):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for row in rows:
        ws.append([_safe(v) for v in row])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.showGridLines = False
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True)
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        ws.column_dimensions[letter].width = min(
            max(max(len(str(cell.value or "")) for cell in col) + 2, 16), 58
        )
    return ws


def _is_system_reference(ref):
    """Suppress only Kubernetes-injected API CA volume refs, not custom ConfigMaps."""
    return (ref.get("kind") == "ConfigMap"
            and ref.get("name") == "kube-root-ca.crt"
            and str(ref.get("via") or "").startswith("volume/kube-api-access-"))


def add_runtime_report_sheets(wb, analysis):
    runtime = analysis.get("runtime_assessment")
    if runtime is None:
        return wb
    resources = runtime.get("resources") or {}
    context = runtime.get("context", "")
    namespace = runtime.get("namespace", "")
    status = runtime.get("collection_status") or {}
    scope = runtime.get("application_scope") or {}
    workload_rows = []
    dependency_rows = []

    for group in ("deployments", "statefulsets", "daemonsets"):
        for workload in resources.get(group) or []:
            workload_rows.append([
                context, namespace, workload.get("kind"), workload.get("name"),
                workload.get("replicas_desired"), workload.get("replicas_ready"),
                ", ".join(workload.get("images") or []), workload.get("service_account"),
                ", ".join(workload.get("configmap_refs") or []),
                ", ".join(workload.get("secret_refs") or []),
                ", ".join(workload.get("pvc_refs") or []), status.get(group, "NOT_REPORTED"),
            ])

    if scope and scope.get("status") != "WORKLOAD_FOUND":
        workload_rows.append([
            context, namespace, "SCOPE STATUS", scope.get("requested_workload"),
            "", "", "", "", "", "", "", scope.get("status"),
        ])

    for group in ("deployments", "statefulsets", "daemonsets", "pods"):
        for workload in resources.get(group) or []:
            for ref in workload.get("dependency_references") or []:
                if _is_system_reference(ref):
                    continue
                dependency_rows.append([
                    context, namespace, workload.get("kind") or "Pod", workload.get("name"),
                    ref.get("kind"), ref.get("name"), ref.get("via"), ref.get("optional"),
                    ref.get("target_status"), ref.get("target_evidence"), ref.get("evidence"),
                ])

    _sheet(wb, "Runtime Workloads",
           ["Context", "Namespace", "Kind", "Workload", "Desired", "Ready",
            "Images", "ServiceAccount", "ConfigMap Refs", "Secret Refs",
            "PVC Refs", "Collection Status"], workload_rows)
    _sheet(wb, "Runtime Dependencies",
           ["Context", "Namespace", "Source Kind", "Source Name",
            "Target Kind", "Target Name", "Reference Via", "Optional",
            "Target Status", "Target Evidence", "Reference Evidence"], dependency_rows)
    return wb
