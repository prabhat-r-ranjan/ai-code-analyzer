
"""Milestone 14: Evidence-based EKS to AKS migration impact assessment."""

from typing import Any


def analyze_migration_impact(
    assessment: dict[str, Any],
) -> dict[str, Any]:
    """Generate migration review findings from static assessment evidence."""

    resources = assessment.get("deployment_details") or []
    chains = assessment.get("end_to_end_dependencies") or []
    config_links = (
        assessment.get("application_configuration_dependencies")
        or []
    )

    findings = []
    seen = set()

    def add_finding(
        rule_id,
        severity,
        category,
        title,
        evidence,
        impact,
        recommendation,
    ):
        # Avoid repeated findings from duplicate dependency chains.
        identity = (
            rule_id,
            str(evidence),
        )

        if identity in seen:
            return

        seen.add(identity)

        findings.append({
            "rule_id": rule_id,
            "severity": severity,
            "category": category,
            "title": title,
            "evidence": evidence,
            "migration_impact": impact,
            "recommendation": recommendation,
            "status": "review_required",
            "runtime_verified": False,
        })

    # -------------------------------------------------
    # RULE 1: Multiple database manifest candidates
    # -------------------------------------------------

    for chain in chains:
        if chain.get("resolution") != "multiple_manifest_candidates":
            continue

        services = chain.get("database_service_candidates") or []
        workloads = chain.get("database_workload_candidates") or []

        add_finding(
            "MIG-001",
            "Medium",
            "Deployment",
            "Multiple database manifest candidates detected",
            {
                "application": (
                    (chain.get("application_workload") or {})
                    .get("name")
                ),
                "service_files": sorted({
                    s.get("source_file")
                    for s in services
                    if s.get("source_file")
                }),
                "workload_files": sorted({
                    w.get("source_file")
                    for w in workloads
                    if w.get("source_file")
                }),
            },
            (
                "Different manifests may represent alternative "
                "deployment definitions or overlays."
            ),
            (
                "Identify the active Helm/Kustomize deployment "
                "configuration before planning AKS migration."
            ),
        )

    # -------------------------------------------------
    # RULE 2: Namespace not explicitly defined
    # -------------------------------------------------

    for resource in resources:
        if resource.get("namespace") is not None:
            continue

        if resource.get("kind") not in {
            "Deployment",
            "StatefulSet",
            "DaemonSet",
            "Service",
            "ConfigMap",
            "Secret",
            "PersistentVolumeClaim",
        }:
            continue

        add_finding(
            "MIG-002",
            "Low",
            "Namespace",
            "Kubernetes namespace not explicitly specified",
            {
                "kind": resource.get("kind"),
                "name": resource.get("name"),
                "source_file": resource.get("file"),
            },
            (
                "The effective namespace depends on deployment "
                "context and may affect resource references."
            ),
            (
                "Verify the target AKS namespace and deployment "
                "overlay. Confirm dependent resources are aligned."
            ),
        )

    # -------------------------------------------------
    # RULE 3: PVC without explicit StorageClass
    # -------------------------------------------------

    for resource in resources:
        if resource.get("kind") != "PersistentVolumeClaim":
            continue

        pvc = resource.get("pvc") or {}

        if pvc.get("storageClassName") is not None:
            continue

        add_finding(
            "MIG-003",
            "Medium",
            "Storage",
            "PVC does not specify a StorageClass",
            {
                "pvc": resource.get("name"),
                "source_file": resource.get("file"),
                "requested_storage": (
                    (pvc.get("resources") or {})
                    .get("requests") or {}
                ).get("storage"),
            },
            (
                "AKS provisioning may depend on the cluster "
                "default StorageClass."
            ),
            (
                "Review Azure Disk/Azure Files requirements, "
                "access modes, default StorageClass and "
                "database data migration strategy."
            ),
        )

    # -------------------------------------------------
    # RULE 4: Secret references require validation
    # -------------------------------------------------

    for link in config_links:
        reference = link.get("reference") or {}

        if reference.get("resource_kind") != "Secret":
            continue

        workload = link.get("workload") or {}

        add_finding(
            "MIG-004",
            "Medium",
            "Secrets",
            "Application depends on Kubernetes Secret",
            {
                "workload": workload.get("name"),
                "source_file": workload.get("source_file"),
                "secret": reference.get("resource_name"),
                "key": reference.get("resource_key"),
                "resolution": link.get("resolution"),
            },
            (
                "The application requires the referenced "
                "Secret and key to be available in AKS."
            ),
            (
                "Validate Secret availability, key names, "
                "namespace and the approved secret-delivery "
                "mechanism. Do not expose credential values."
            ),
        )

    # -------------------------------------------------
    # RULE 5: Database connectivity dependency
    # -------------------------------------------------

    for chain in chains:
        endpoint = (
            (chain.get("configuration") or {})
            .get("database_endpoint") or {}
        )

        if not endpoint.get("host"):
            continue

        add_finding(
            "MIG-005",
            "Medium",
            "Network",
            "Application database connectivity requires validation",
            {
                "application": (
                    (chain.get("application_workload") or {})
                    .get("name")
                ),
                "database_host": endpoint.get("host"),
                "database_port": endpoint.get("port"),
                "database_name": endpoint.get("database_name"),
            },
            (
                "Database access may be affected by AKS "
                "networking, DNS, policies or authentication."
            ),
            (
                "Validate DNS resolution, TCP connectivity, "
                "network policies, TLS requirements and "
                "database authentication from AKS."
            ),
        )

    # -------------------------------------------------
    # RULE 6: Azure Container Registry image
    # -------------------------------------------------

    for resource in resources:
        if resource.get("kind") not in {
            "Deployment",
            "StatefulSet",
            "DaemonSet",
            "Pod",
        }:
            continue

        for container in resource.get("containers") or []:
            image = container.get("image") or ""

            if not isinstance(image, str):
                continue

            registry = image.split("/", 1)[0].lower()

            if not registry.endswith(".azurecr.io"):
                continue

            add_finding(
                "MIG-006",
                "Low",
                "Container Registry",
                "Container image hosted in Azure Container Registry",
                {
                    "workload": resource.get("name"),
                    "container": container.get("name"),
                    "image": image,
                    "source_file": resource.get("file"),
                },
                (
                    "AKS must have permission and network "
                    "access to pull the container image."
                ),
                (
                    "Validate AKS kubelet identity, ACR "
                    "repository permissions, network access "
                    "and image availability."
                ),
            )

    severity_order = {
        "High": 0,
        "Medium": 1,
        "Low": 2,
        "Info": 3,
    }

    findings.sort(
        key=lambda item: (
            severity_order.get(item["severity"], 99),
            item["rule_id"],
            item["title"],
        )
    )

    summary = {
        "total_findings": len(findings),
        "high": sum(
            f["severity"] == "High" for f in findings
        ),
        "medium": sum(
            f["severity"] == "Medium" for f in findings
        ),
        "low": sum(
            f["severity"] == "Low" for f in findings
        ),
        "info": sum(
            f["severity"] == "Info" for f in findings
        ),
        "runtime_verified": False,
        "assessment_type": "static_repository_assessment",
    }

    return {
        "migration_impact_summary": summary,
        "migration_impact_findings": findings,
    }
