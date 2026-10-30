
"""Milestone 13.2: Refined application-to-Kubernetes database correlation."""

from typing import Any


WORKLOAD_KINDS = {
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Pod",
}


def _namespace_compatible(source_ns, target_ns):
    """Reject explicit namespace conflicts; unknown remains unverified."""
    return (
        source_ns is None
        or target_ns is None
        or source_ns == target_ns
    )


def _resource_identity(resource):
    return {
        "kind": resource.get("kind"),
        "name": resource.get("name"),
        "namespace": resource.get("namespace"),
        "source_file": resource.get("file"),
    }


def _get_workload_pvc_references(workload):
    """Read PVC names actually referenced by a workload."""
    references = []

    pod = workload.get("pod") or {}

    for volume in pod.get("volumes") or []:
        if not isinstance(volume, dict):
            continue

        claim = volume.get("persistentVolumeClaim")

        if isinstance(claim, dict):
            name = claim.get("claimName")

            if name and name not in references:
                references.append(name)

    return references


def _match_pvcs(workload, resources):
    """Associate PVC definitions only with referencing workloads."""
    references = _get_workload_pvc_references(workload)
    matched = []

    for claim_name in references:
        candidates = [
            r for r in resources
            if r.get("kind") == "PersistentVolumeClaim"
            and r.get("name") == claim_name
            and _namespace_compatible(
                workload.get("namespace"),
                r.get("namespace"),
            )
        ]

        if not candidates:
            matched.append({
                "name": claim_name,
                "source_file": None,
                "resolution": "pvc_definition_not_found",
            })
            continue

        for pvc in candidates:
            pvc_config = pvc.get("pvc") or {}

            matched.append({
                "name": claim_name,
                "namespace": pvc.get("namespace"),
                "source_file": pvc.get("file"),
                "storage": (
                    (pvc_config.get("resources") or {})
                    .get("requests") or {}
                ).get("storage"),
                "storage_class": pvc_config.get(
                    "storageClassName"
                ),
                "resolution": (
                    "unique_candidate_namespace_unverified"
                    if (
                        workload.get("namespace") is None
                        or pvc.get("namespace") is None
                    )
                    else "manifest_match"
                ) if len(candidates) == 1
                else "multiple_manifest_candidates",
            })

    return matched


def correlate_application_dependencies(
    database_details: list[dict[str, Any]],
    deployment_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build candidate database chains from static repository evidence."""

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

        service_name = str(host).split(".")[0]

        # A host such as postgres.default.svc.cluster.local
        # may imply a namespace. Short names remain uncertain.
        host_parts = str(host).split(".")
        dns_namespace = (
            host_parts[1]
            if len(host_parts) >= 3
            and host_parts[2] == "svc"
            else None
        )

        matching_services = []

        for svc in services:
            if svc.get("name") != service_name:
                continue

            if (
                dns_namespace is not None
                and svc.get("namespace") is not None
                and svc.get("namespace") != dns_namespace
            ):
                continue

            service_ports = (
                (svc.get("service") or {})
                .get("ports") or []
            )

            if port is not None and not any(
                str(p.get("port")) == str(port)
                for p in service_ports
                if isinstance(p, dict)
            ):
                continue

            matching_services.append(svc)

        database_info = {
            "type": database.get("database_type"),
            "host": host,
            "port": port,
            "database_name": database.get("database_name"),
        }

        source_info = {
            "type": "Application Configuration",
            "file": database.get("source_file"),
        }

        if not matching_services:
            relationships.append({
                "relationship": "application_uses_database",
                "source": source_info,
                "database": database_info,
                "kubernetes_service": None,
                "candidate_workloads": [],
                "candidate_pvcs": [],
                "resolution": "service_not_found_in_manifests",
                "runtime_verified": False,
                "validation_required": (
                    "Check external database services, other "
                    "repositories, namespaces and Helm/Kustomize."
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

                if not _namespace_compatible(
                    svc.get("namespace"),
                    workload.get("namespace"),
                ):
                    continue

                workload_pvcs = _match_pvcs(
                    workload,
                    deployment_details,
                )

                workload_info = _resource_identity(workload)

                # Each workload now owns its PVC references.
                workload_info["pvc_references"] = workload_pvcs

                candidate_workloads.append(workload_info)

                # Preserve the old top-level field for compatibility.
                for pvc in workload_pvcs:
                    if pvc not in candidate_pvcs:
                        candidate_pvcs.append(pvc)

            # Candidate count refers to source manifest definitions,
            # not the number of running resources.
            candidate_count = len(candidate_workloads)

            if candidate_count > 1:
                resolution = "multiple_manifest_candidates"
            elif candidate_count == 1:
                resolution = (
                    "unique_candidate_namespace_unverified"
                    if (
                        svc.get("namespace") is None
                        or candidate_workloads[0].get(
                            "namespace"
                        ) is None
                    )
                    else "candidate_manifest_chain"
                )
            else:
                resolution = "service_found_workload_unresolved"

            relationships.append({
                "relationship": "application_uses_database",
                "source": source_info,
                "database": database_info,
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
                "manifest_service_candidates": len(
                    matching_services
                ),
                "manifest_workload_candidates": candidate_count,
                "resolution": resolution,
                "runtime_verified": False,
                "validation_required": (
                    "Confirm active deployment overlay, effective "
                    "namespace, Service endpoints, database "
                    "connectivity and persistent storage."
                ),
            })

    return relationships


def correlate_application_configuration(
    deployment_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Correlate workload environment references with ConfigMaps and Secrets."""

    relationships = []

    workloads = [
        r for r in deployment_details
        if r.get("kind") in WORKLOAD_KINDS
    ]

    for workload in workloads:
        workload_ns = workload.get("namespace")

        containers = (
            (workload.get("containers") or [])
            + (workload.get("initContainers") or [])
        )

        for container in containers:
            references = []

            for env in container.get("env") or []:
                if not isinstance(env, dict):
                    continue

                value_from = env.get("valueFrom") or {}

                for ref_type, resource_kind in (
                    ("configMapKeyRef", "ConfigMap"),
                    ("secretKeyRef", "Secret"),
                ):
                    ref = value_from.get(ref_type)

                    if not isinstance(ref, dict):
                        continue

                    if not ref.get("name"):
                        continue

                    references.append({
                        "resource_kind": resource_kind,
                        "resource_name": ref["name"],
                        "resource_key": ref.get("key"),
                        "environment_variable": env.get("name"),
                        "reference_type": ref_type,
                    })

            for env_from in container.get("envFrom") or []:
                if not isinstance(env_from, dict):
                    continue

                for ref_type, resource_kind in (
                    ("configMapRef", "ConfigMap"),
                    ("secretRef", "Secret"),
                ):
                    ref = env_from.get(ref_type)

                    if not isinstance(ref, dict):
                        continue

                    if not ref.get("name"):
                        continue

                    references.append({
                        "resource_kind": resource_kind,
                        "resource_name": ref["name"],
                        "resource_key": None,
                        "environment_variable": None,
                        "reference_type": ref_type,
                    })

            for reference in references:
                candidates = [
                    r for r in deployment_details
                    if (
                        r.get("kind")
                        == reference["resource_kind"]
                        and r.get("name")
                        == reference["resource_name"]
                        and _namespace_compatible(
                            workload_ns,
                            r.get("namespace"),
                        )
                    )
                ]

                if not candidates:
                    resolution = "resource_not_found"
                elif len(candidates) > 1:
                    resolution = "multiple_manifest_candidates"
                elif (
                    workload_ns is None
                    or candidates[0].get("namespace") is None
                ):
                    resolution = "unique_candidate_namespace_unverified"
                else:
                    resolution = "manifest_match"

                candidate_resources = []

                for resource in candidates:
                    resource_info = _resource_identity(resource)

                    if reference["resource_kind"] == "ConfigMap":
                        config = resource.get("configMap") or {}

                        resource_info["available_keys"] = (
                            config.get("keys") or []
                        )

                        # Only previously sanitized JDBC endpoints.
                        resource_info["database_endpoints"] = (
                            config.get("database_endpoints") or {}
                        )

                    else:
                        secret = resource.get("secret") or {}

                        # Secret names and keys only. Never values.
                        resource_info["available_keys"] = (
                            secret.get("keys") or []
                        )

                    candidate_resources.append(resource_info)

                relationships.append({
                    "relationship": "workload_uses_configuration",
                    "workload": _resource_identity(workload),
                    "container": container.get("name"),
                    "reference": reference,
                    "candidate_resources": candidate_resources,
                    "resolution": resolution,
                    "runtime_verified": False,
                })

    return relationships


def correlate_end_to_end_dependencies(
    database_details: list[dict[str, Any]],
    deployment_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build evidence-based application-to-database dependency chains.

    Static manifest evidence only; no runtime verification.
    """
    from urllib.parse import urlsplit

    database_chains = correlate_application_dependencies(
        database_details,
        deployment_details,
    )
    configuration_links = correlate_application_configuration(
        deployment_details
    )

    def parse_jdbc_endpoint(value):
        if not isinstance(value, str):
            return None

        if not value.startswith("jdbc:"):
            return None

        try:
            parsed = urlsplit(value[5:])

            if (
                not parsed.scheme
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                return None

            return {
                "database_type": parsed.scheme,
                "host": parsed.hostname,
                "port": parsed.port,
                "database_name": (
                    parsed.path.lstrip("/") or None
                ),
            }
        except ValueError:
            return None

    def matching_database_chains(endpoint, namespace):
        matched = []

        for chain in database_chains:
            database = chain.get("database") or {}

            if (
                str(database.get("host", "")).lower()
                != str(endpoint["host"]).lower()
            ):
                continue

            if (
                endpoint["port"] is not None
                and str(database.get("port"))
                != str(endpoint["port"])
            ):
                continue

            if (
                endpoint["database_name"]
                and database.get("database_name")
                and endpoint["database_name"]
                != database["database_name"]
            ):
                continue

            service = chain.get("kubernetes_service")

            if service and not _namespace_compatible(
                namespace,
                service.get("namespace"),
            ):
                continue

            matched.append(chain)

        return matched

    def candidate_identity(candidate):
        return {
            "kind": candidate.get("kind"),
            "name": candidate.get("name"),
            "namespace": candidate.get("namespace"),
            "source_file": candidate.get("source_file"),
        }

    chains = []

    # Group configuration references by the exact workload manifest
    # and container. Avoid mixing alternative manifest definitions.
    grouped = {}

    for link in configuration_links:
        workload = link.get("workload") or {}

        key = (
            workload.get("kind"),
            workload.get("name"),
            workload.get("namespace"),
            workload.get("source_file"),
            link.get("container"),
        )

        if key not in grouped:
            grouped[key] = {
                "workload": workload,
                "container": link.get("container"),
                "links": [],
            }

        grouped[key]["links"].append(link)

    for group in grouped.values():
        workload = group["workload"]
        workload_ns = workload.get("namespace")

        config_references = []
        secret_references = []
        endpoint_candidates = []

        for link in group["links"]:
            reference = link.get("reference") or {}
            kind = reference.get("resource_kind")

            matched_resources = link.get(
                "candidate_resources"
            ) or []

            reference_summary = {
                "resource_name": reference.get("resource_name"),
                "resource_key": reference.get("resource_key"),
                "environment_variable": reference.get(
                    "environment_variable"
                ),
                "reference_type": reference.get(
                    "reference_type"
                ),
                "candidate_resources": [
                    candidate_identity(resource)
                    for resource in matched_resources
                ],
                "resolution": link.get("resolution"),
            }

            if kind == "Secret":
                # Only references and key names; never values.
                secret_references.append(reference_summary)
                continue

            if kind != "ConfigMap":
                continue

            config_references.append(reference_summary)

            for resource in matched_resources:
                endpoints = resource.get(
                    "database_endpoints"
                ) or {}

                for config_key, jdbc_url in endpoints.items():
                    ref_type = reference.get("reference_type")

                    # configMapKeyRef consumes one specific key.
                    if ref_type == "configMapKeyRef":
                        if config_key != reference.get("resource_key"):
                            continue

                    # envFrom imports keys, optionally with a prefix.
                    elif ref_type == "configMapRef":
                        if reference.get("resource_key") is not None:
                            continue
                    else:
                        continue

                    endpoint = parse_jdbc_endpoint(jdbc_url)

                    if endpoint is None:
                        continue

                    endpoint_candidates.append({
                        "configmap": candidate_identity(resource),
                        "configuration_key": config_key,
                        "database_endpoint": endpoint,
                        "configuration_resolution": link.get(
                            "resolution"
                        ),
                    })

        # Deduplicate endpoints within the same container.
        unique_endpoints = []

        for candidate in endpoint_candidates:
            if candidate not in unique_endpoints:
                unique_endpoints.append(candidate)

        for candidate in unique_endpoints:
            endpoint = candidate["database_endpoint"]

            matched_chains = matching_database_chains(
                endpoint,
                workload_ns,
            )

            service_candidates = []
            database_workloads = []
            pvc_candidates = []

            for db_chain in matched_chains:
                service = db_chain.get("kubernetes_service")

                if service and service not in service_candidates:
                    service_candidates.append(service)

                for db_workload in (
                    db_chain.get("candidate_workloads") or []
                ):
                    if db_workload not in database_workloads:
                        database_workloads.append(db_workload)

                    for pvc in (
                        db_workload.get("pvc_references") or []
                    ):
                        if pvc not in pvc_candidates:
                            pvc_candidates.append(pvc)

            if not matched_chains:
                resolution = "database_chain_not_found"
            elif not service_candidates:
                resolution = "database_service_not_found"
            elif (
                len(service_candidates) > 1
                or len(database_workloads) > 1
                or candidate["configuration_resolution"]
                == "multiple_manifest_candidates"
            ):
                resolution = "multiple_manifest_candidates"
            elif not database_workloads:
                resolution = "database_workload_unresolved"
            else:
                resolution = (
                    "candidate_chain_namespace_unverified"
                    if (
                        workload_ns is None
                        or any(
                            service.get("namespace") is None
                            for service in service_candidates
                        )
                    )
                    else "candidate_manifest_chain"
                )

            chains.append({
                "relationship": (
                    "application_to_database_dependency_chain"
                ),
                "application_workload": workload,
                "container": group["container"],
                "configuration": {
                    "configmap": candidate["configmap"],
                    "key": candidate["configuration_key"],
                    "database_endpoint": endpoint,
                },
                "configmap_references": config_references,
                "secret_references": secret_references,
                "database_service_candidates": service_candidates,
                "database_workload_candidates": database_workloads,
                "pvc_candidates": pvc_candidates,
                "resolution": resolution,
                "runtime_verified": False,
                "validation_required": (
                    "Confirm active Kustomize/Helm overlay, "
                    "effective namespace, configuration precedence, "
                    "database connectivity, Service endpoints, "
                    "storage and Secret availability."
                ),
            })

    return chains

