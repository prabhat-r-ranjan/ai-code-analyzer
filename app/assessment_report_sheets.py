"""Milestone 15.1: Kubernetes LLD and migration assessment Excel sheets."""

import json

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def _display(value):
    """Convert nested assessment values into readable Excel text."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    text = str(value)
    return "\u0027" + text if text.startswith(("=", "+", "-", "@")) else text


def _resource_label(resource):
    if not resource:
        return ""
    return f"{resource.get('kind', '')}/{resource.get('name', '')}"


def _names(items):
    return ", ".join(sorted({str(item.get("name")) for item in items if item.get("name")}))


def _files(items):
    return ", ".join(sorted({str(item.get("source_file")) for item in items if item.get("source_file")}))


def _style_sheet(ws):
    ws.freeze_panes = "A2"
    ws.sheet_view.showGridLines = False
    ws.auto_filter.ref = ws.dimensions

    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    ws.row_dimensions[1].height = 32

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="EDF3F8")

    for column in ws.columns:
        letter = get_column_letter(column[0].column)
        lengths = [len(str(cell.value or "")) for cell in column]
        ws.column_dimensions[letter].width = min(max(max(lengths, default=12) + 2, 16), 55)


def _add_sheet(wb, title, headers, rows):
    if title in wb.sheetnames:
        del wb[title]

    ws = wb.create_sheet(title)
    ws.append(headers)
    for row in rows:
        ws.append([_display(value) for value in row])
    _style_sheet(ws)
    return ws


def _format_env_references(container):
    """Only export reference names/keys; never export Secret values."""
    references = []

    for env in container.get("env") or []:
        if not isinstance(env, dict):
            continue
        value_from = env.get("valueFrom") or {}
        for ref_type, label in (("configMapKeyRef", "ConfigMap"), ("secretKeyRef", "Secret")):
            ref = value_from.get(ref_type) or {}
            if isinstance(ref, dict) and ref.get("name"):
                key = ref.get("key") or ""
                references.append(f"{label}: {ref['name']}/{key}")

    for env_from in container.get("envFrom") or []:
        if not isinstance(env_from, dict):
            continue
        for ref_type, label in (("configMapRef", "ConfigMap"), ("secretRef", "Secret")):
            ref = env_from.get(ref_type) or {}
            if isinstance(ref, dict) and ref.get("name"):
                references.append(f"{label}: {ref['name']} (all keys)")

    return "; ".join(sorted(set(references)))


def _build_kubernetes_lld_rows(resources):
    """One row per manifest resource; preserve missing vs explicit values."""
    rows = []
    for resource in resources:
        kind = resource.get("kind") or ""
        containers = (resource.get("containers") or []) + (resource.get("initContainers") or [])
        pod = resource.get("pod") or {}
        service = resource.get("service") or {}
        pvc = resource.get("pvc") or {}
        hpa = resource.get("hpa") or {}
        ingress = resource.get("ingress") or {}
        configmap = resource.get("configMap") or {}
        secret = resource.get("secret") or {}

        names = []
        images = []
        ports = []
        env_refs = []
        cpu_requests = []
        memory_requests = []
        cpu_limits = []
        memory_limits = []
        liveness = []
        readiness = []
        startup = []
        mounts = []
        for c in containers:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "unnamed")
            names.append(name)
            if c.get("image"):
                images.append(f"{name}: {c['image']}")
            ports.extend(f"{name}: {v}" for v in (c.get("ports") or []))
            ref = _format_env_references(c)
            if ref:
                env_refs.append(f"{name}: {ref}")
            for field, dest in (("cpu_request", cpu_requests),
                                ("memory_request", memory_requests),
                                ("cpu_limit", cpu_limits),
                                ("memory_limit", memory_limits)):
                if c.get(field) is not None:
                    dest.append(f"{name}: {c[field]}")
            for field, dest in (("livenessProbe", liveness),
                                ("readinessProbe", readiness),
                                ("startupProbe", startup)):
                if c.get(field):
                    dest.append(f"{name}: {_display(c[field])}")
            for mount in c.get("volumeMounts") or []:
                if isinstance(mount, dict):
                    mounts.append(f"{name}: {mount.get('name', '')} -> {mount.get('mountPath', '')}")

        for port in service.get("ports") or []:
            if isinstance(port, dict):
                ports.append(f"{port.get('port', '')} -> {port.get('targetPort', '')}/{port.get('protocol') or 'TCP'}")

        claims = []
        for volume in pod.get("volumes") or []:
            if isinstance(volume, dict):
                claim = volume.get("persistentVolumeClaim") or {}
                if isinstance(claim, dict) and claim.get("claimName"):
                    claims.append(str(claim["claimName"]))

        ingress_routes = []
        for rule in ingress.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            for path in rule.get("paths") or []:
                if isinstance(path, dict):
                    ingress_routes.append(
                        f"{rule.get('host') or '*'}{path.get('path') or '/'} -> "
                        f"{path.get('serviceName') or '?'}:{_display(path.get('servicePort'))}"
                    )

        target = hpa.get("scaleTargetRef") or {}
        hpa_target = (f"{target.get('kind', '')}/{target.get('name', '')}"
                      if target else "")
        storage = ((pvc.get("resources") or {}).get("requests") or {}).get("storage")
        replicas = resource.get("replicas")

        rows.append([
            kind,
            resource.get("name"),
            resource.get("namespace") if resource.get("namespace") is not None else "Not specified",
            resource.get("file"),
            replicas if replicas is not None else ("Not specified (Kubernetes default may apply)" if kind in {"Deployment", "StatefulSet"} else ""),
            "; ".join(names),
            "; ".join(images),
            "; ".join(ports),
            service.get("type") if kind == "Service" else "",
            _display(service.get("selector")) if service.get("selector") else "",
            "; ".join(env_refs),
            pod.get("serviceAccountName") or ("Not specified" if kind in {"Deployment", "StatefulSet", "DaemonSet", "Pod", "Job", "CronJob"} else ""),
            _display(pod.get("imagePullSecrets")) if pod.get("imagePullSecrets") else "",
            "; ".join(cpu_requests),
            "; ".join(memory_requests),
            "; ".join(cpu_limits),
            "; ".join(memory_limits),
            "; ".join(liveness),
            "; ".join(readiness),
            "; ".join(startup),
            "; ".join(sorted(set(claims))),
            "; ".join(mounts),
            storage,
            (pvc.get("storageClassName") if pvc.get("storageClassName") is not None else "Not specified") if kind == "PersistentVolumeClaim" else "",
            ", ".join(pvc.get("accessModes") or []),
            hpa_target,
            hpa.get("minReplicas") if kind == "HorizontalPodAutoscaler" else "",
            hpa.get("maxReplicas") if kind == "HorizontalPodAutoscaler" else "",
            _display(hpa.get("metrics")) if hpa.get("metrics") else "",
            ingress.get("ingressClassName") if kind == "Ingress" else "",
            "; ".join(ingress_routes),
            ", ".join(configmap.get("keys") or []),
            ", ".join(secret.get("keys") or []),
            "Static manifest evidence",
            "Runtime not verified",
        ])
    return rows


def _compact_lld_rows(resources):
    """Present all 35 existing LLD fields in 12 grouped, readable columns."""
    raw_rows = _build_kubernetes_lld_rows(resources)

    def lines(*pairs):
        return "\n".join(f"{label}: {value}" for label, value in pairs
                         if value is not None and str(value).strip())

    rows = []
    for v in raw_rows:
        # Indices follow the original 35-field LLD schema.
        workload = lines(("Replicas", v[4]), ("Containers", v[5]),
                         ("Images", v[6]), ("Ports", v[7]))
        network = lines(("Service type", v[8]), ("Selector", v[9]),
                        ("Ingress class", v[29]), ("Ingress routes", v[30]))
        compute = lines(("CPU request", v[13]), ("Memory request", v[14]),
                        ("CPU limit", v[15]), ("Memory limit", v[16]))
        probes = lines(("Liveness", v[17]), ("Readiness", v[18]),
                       ("Startup", v[19]))
        identity = lines(("ServiceAccount", v[11]),
                         ("Image pull secrets", v[12]),
                         ("Config/Secret refs", v[10]),
                         ("ConfigMap keys", v[31]), ("Secret keys", v[32]))
        storage = lines(("PVC references", v[20]), ("Volume mounts", v[21]),
                        ("Storage requested", v[22]), ("StorageClass", v[23]),
                        ("Access modes", v[24]))
        scaling = lines(("HPA target", v[25]), ("HPA min", v[26]),
                        ("HPA max", v[27]), ("HPA metrics", v[28]))
        rows.append([
            v[0], v[1], v[2], v[3], workload, network,
            compute, probes, identity, storage, scaling,
            lines(("Evidence", v[33]), ("Validation", v[34])),
        ])
    return rows


def add_assessment_report_sheets(wb, result):
    """Extend existing workbook with LLD, dependency, findings and notes sheets."""
    resources = result.get("deployment_details") or []
    chains = result.get("end_to_end_dependencies") or []
    findings = result.get("migration_impact_findings") or []
    summary = result.get("migration_impact_summary") or {}

    lld_ws = _add_sheet(
        wb,
        "Kubernetes LLD",
        [
            "Resource Kind", "Resource Name", "Namespace", "Source File",
            "Workload / Image / Ports", "Service / Ingress",
            "CPU / Memory", "Health Probes", "Identity / Config / Secrets",
            "Storage / Volumes", "HPA / Scaling", "Evidence / Validation",
        ],
        _compact_lld_rows(resources),
    )
    # A compact overview: detailed multiline cells can be read in the formula bar.
    # Avoid huge row heights when a resource has extensive nested configuration.
    for row in range(2, lld_ws.max_row + 1):
        lld_ws.row_dimensions[row].height = 75
    for col in range(5, 13):
        lld_ws.column_dimensions[get_column_letter(col)].width = 42
    lld_ws.column_dimensions["D"].width = 48

    chain_rows = []
    for chain in chains:
        config = chain.get("configuration") or {}
        endpoint = config.get("database_endpoint") or {}
        secret_refs = chain.get("secret_references") or []
        services = chain.get("database_service_candidates") or []
        workloads = chain.get("database_workload_candidates") or []
        pvcs = chain.get("pvc_candidates") or []
        chain_rows.append([
            _resource_label(chain.get("application_workload")),
            chain.get("container"),
            (config.get("configmap") or {}).get("name"),
            config.get("key"),
            endpoint.get("database_type"),
            endpoint.get("host"),
            endpoint.get("port"),
            endpoint.get("database_name"),
            ", ".join(sorted({str(ref.get("resource_name")) for ref in secret_refs if ref.get("resource_name")})),
            ", ".join(sorted({str(ref.get("resource_key")) for ref in secret_refs if ref.get("resource_key")})),
            _names(services),
            _files(services),
            _names(workloads),
            _files(workloads),
            _names(pvcs),
            ", ".join(sorted({str(pvc.get("storage")) for pvc in pvcs if pvc.get("storage")})),
            chain.get("resolution"),
            chain.get("runtime_verified"),
            chain.get("validation_required"),
        ])

    _add_sheet(
        wb,
        "Dependency Chains",
        [
            "Application Workload", "Container", "ConfigMap", "Config Key",
            "Database Type", "Database Host", "Database Port", "Database Name",
            "Secret Names", "Secret Keys", "Database Services", "Service Source Files",
            "Database Workloads", "Workload Source Files", "PVC Names", "PVC Storage",
            "Resolution", "Runtime Verified", "Validation Required",
        ],
        chain_rows,
    )

    finding_rows = []
    for finding in findings:
        finding_rows.append([
            finding.get("rule_id"), finding.get("severity"), finding.get("category"),
            finding.get("title"), finding.get("evidence"), finding.get("migration_impact"),
            finding.get("recommendation"), finding.get("status"),
            finding.get("runtime_verified"),
        ])

    findings_ws = _add_sheet(
        wb,
        "Migration Findings",
        [
            "Rule ID", "Severity", "Category", "Finding", "Evidence",
            "Migration Impact", "Recommendation", "Status", "Runtime Verified",
        ],
        finding_rows,
    )

    severity_colors = {"High": "F4CCCC", "Medium": "FCE5CD", "Low": "FFF2CC", "Info": "D9EAD3"}
    for row in range(2, findings_ws.max_row + 1):
        cell = findings_ws.cell(row=row, column=2)
        color = severity_colors.get(cell.value)
        if color:
            cell.fill = PatternFill("solid", fgColor=color)

    notes = [
        ["Repository", result.get("repository")],
        ["Branch", result.get("branch")],
        ["Assessment Type", summary.get("assessment_type")],
        ["Total Findings", summary.get("total_findings", len(findings))],
        ["High Findings", summary.get("high", 0)],
        ["Medium Findings", summary.get("medium", 0)],
        ["Low Findings", summary.get("low", 0)],
        ["Source Client Calls Detected", result.get("source_client_evidence_count", 0)],
        ["Source Client Validation", "Static call candidates only; effective target and runtime connectivity not verified."],
        ["Runtime Inventory Collected", bool((result.get("runtime_assessment") or {}).get("runtime_verified", False))],
        ["Runtime Workload Scope", (result.get("runtime_assessment") or {}).get("application_scope", {}).get("requested_workload") or "Not specified"],
        ["Runtime Verified", False],
        ["Analysis Scope", "Static repository and Kubernetes manifest analysis; optional read-only runtime inventory"],
        ["Important Limitation", "Candidate dependencies are not confirmed runtime topology."],
        ["Deployment Validation", "Confirm active Helm/Kustomize overlays and namespaces."],
        ["Connectivity Validation", "Validate DNS, TCP, TLS and authentication in AKS."],
        ["Security", "Secret references only; do not export credential values."],
    ]
    _add_sheet(wb, "Assessment Notes", ["Property", "Value"], notes)
    return wb
