
"""Milestone 13: Application-to-Kubernetes database correlation."""

from typing import Any


WORKLOAD_KINDS = {
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Pod",
}


def correlate_application_dependencies(
    database_details: list[dict[str, Any]],
    deployment_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify potential database dependency chains from static evidence."""

    relationships = []

    services = [
        r for r in deployment_details
        if r.get("kind") == "Service"
    ]

    workloads = [
        r for r in deployment_details
        if r.get("kind") in WORKLOAD_KINDS
    ]

    for database in database_details:
        host = database.get("host")
        port = database.get("port")

        if not host:
            continue

        # A Kubernetes DNS name may be short or fully qualified.
        # This is a candidate match, not runtime confirmation.
        service_name = str(host).split(".")[0]

        matching_services = [
            svc for svc in services
            if svc.get("name") == service_name
            and (
                port is None
                or any(
                    str(p.get("port")) == str(port)
                    for p in (
                        (svc.get("service") or {})
                        .get("ports") or []
                    )
                )
            )
        ]

        if not matching_services:
            relationships.append({
                "relationship": "application_uses_database",
                "source": {
                    "type": "Application Configuration",
                    "file": database.get("source_file"),
                },
                "database": {
                    "type": database.get("database_type"),
                    "host": host,
                    "port": port,
                    "database_name": database.get("database_name"),
                },
                "kubernetes_service": None,
                "candidate_workloads": [],
                "candidate_pvcs": [],
                "resolution": "service_not_found_in_manifests",
                "runtime_verified": False,
                "validation_required": (
                    "Confirm whether the database is external, "
                    "provided by another namespace/repository, "
                    "or created by Helm/Kustomize."
                ),
            })
            continue

        for svc in matching_services:
            selector = (
                (svc.get("service") or {})
                .get("selector") or {}
            )

            candidate_workloads = []
            candidate_pvcs = []

            for workload in workloads:
                labels = (
                    (workload.get("pod") or {})
                    .get("templateLabels") or {}
                )

                if not selector or not labels:
                    continue

                if not all(
                    labels.get(key) == value
                    for key, value in selector.items()
                ):
                    continue

                # Explicitly conflicting namespaces cannot match.
                svc_ns = svc.get("namespace")
                workload_ns = workload.get("namespace")

                if (
                    svc_ns is not None
                    and workload_ns is not None
                    and svc_ns != workload_ns
                ):
                    continue

                candidate_workloads.append({
                    "kind": workload.get("kind"),
                    "name": workload.get("name"),
                    "namespace": workload_ns,
                    "source_file": workload.get("file"),
                })

                for volume in (
                    (workload.get("pod") or {})
                    .get("volumes") or []
                ):
                    claim = (
                        volume.get("persistentVolumeClaim")
                        if isinstance(volume, dict)
                        else None
                    )

                    if not isinstance(claim, dict):
                        continue

                    claim_name = claim.get("claimName")

                    for pvc in deployment_details:
                        if (
                            pvc.get("kind")
                            == "PersistentVolumeClaim"
                            and pvc.get("name") == claim_name
                            and (
                                workload_ns is None
                                or pvc.get("namespace") is None
                                or workload_ns
                                == pvc.get("namespace")
                            )
                        ):
                            item = {
                                "name": claim_name,
                                "namespace": pvc.get("namespace"),
                                "source_file": pvc.get("file"),
                                "storage": (
                                    (pvc.get("pvc") or {})
                                    .get("resources") or {}
                                ).get("requests", {}).get("storage"),
                                "storage_class": (
                                    (pvc.get("pvc") or {})
                                    .get("storageClassName")
                                ),
                            }

                            if item not in candidate_pvcs:
                                candidate_pvcs.append(item)

            relationships.append({
                "relationship": "application_uses_database",
                "source": {
                    "type": "Application Configuration",
                    "file": database.get("source_file"),
                },
                "database": {
                    "type": database.get("database_type"),
                    "host": host,
                    "port": port,
                    "database_name": database.get("database_name"),
                },
                "kubernetes_service": {
                    "name": svc.get("name"),
                    "namespace": svc.get("namespace"),
                    "source_file": svc.get("file"),
                    "ports": (
                        (svc.get("service") or {})
                        .get("ports") or []
                    ),
                },
                "candidate_workloads": candidate_workloads,
                "candidate_pvcs": candidate_pvcs,
                "resolution": (
                    "candidate_manifest_chain"
                    if candidate_workloads
                    else "service_found_workload_unresolved"
                ),
                "runtime_verified": False,
                "validation_required": (
                    "Confirm effective application configuration, "
                    "deployment overlay, namespace, service endpoints, "
                    "database connectivity and storage in the live cluster."
                ),
            })

    return relationships
