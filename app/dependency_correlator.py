"""Milestone 12: Static Kubernetes dependency correlation."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


WORKLOADS = {
    "Deployment", "StatefulSet", "DaemonSet",
    "Job", "CronJob", "Pod"
}

NAMESPACED = {
    "Deployment", "StatefulSet", "DaemonSet",
    "Job", "CronJob", "Pod", "Service",
    "ConfigMap", "Secret", "ServiceAccount",
    "PersistentVolumeClaim", "HorizontalPodAutoscaler",
    "Ingress"
}


def _identity(resource: dict) -> dict:
    return {
        "kind": resource.get("kind"),
        "name": resource.get("name"),
        "namespace": resource.get("namespace"),
        "source_file": resource.get("file"),
        "document_index": resource.get("document_index"),
    }


def correlate_dependencies(
    resources: list[dict[str, Any]]
) -> dict[str, Any]:

    by_kind_name = defaultdict(list)

    for r in resources:
        if isinstance(r, dict) and r.get("kind") and r.get("name"):
            by_kind_name[(r["kind"], r["name"])].append(r)

    relationships = []
    findings = []

    seen_relations = set()
    seen_findings = set()

    def finding(
        code,
        severity,
        subject,
        message,
        evidence,
        recommendation,
        status="Requires Runtime Validation",
    ):
        key = (
            code,
            subject.get("kind"),
            subject.get("name"),
            subject.get("namespace"),
            subject.get("file"),
            evidence,
        )

        if key in seen_findings:
            return

        seen_findings.add(key)

        findings.append({
            "code": code,
            "severity": severity,
            "subject": _identity(subject),
            "message": message,
            "evidence": evidence,
            "migration_impact": recommendation,
            "validation_status": status,
        })

    def link(
        source,
        kind,
        name,
        relation,
        evidence,
        *,
        target_namespace=None,
        optional=False,
    ):
        if not isinstance(name, str) or not name.strip():
            return

        ns = (
            source.get("namespace")
            if target_namespace is None
            else target_namespace
        )

        candidates = by_kind_name.get((kind, name), [])

        compatible = [
            r for r in candidates
            if (
                kind not in NAMESPACED
                or ns is None
                or r.get("namespace") is None
                or r.get("namespace") == ns
            )
        ]

        exact = [
            r for r in compatible
            if (
                kind not in NAMESPACED
                or (
                    ns is not None
                    and r.get("namespace") == ns
                )
            )
        ]

        if len(exact) == 1 and len(compatible) == 1:
            status = "manifest_match"
        elif len(compatible) == 1:
            status = "unique_candidate_namespace_unverified"
        elif len(compatible) > 1:
            status = "ambiguous_manifest_candidates"
        else:
            status = "not_found_in_scanned_manifests"

        key = (
            source.get("file"),
            source.get("document_index"),
            source.get("kind"),
            source.get("name"),
            kind,
            name,
            relation,
            evidence,
        )

        if key in seen_relations:
            return

        seen_relations.add(key)

        relationships.append({
            "source": _identity(source),
            "target": {
                "kind": kind,
                "name": name,
                "namespace": ns,
            },
            "relationship": relation,
            "evidence": evidence,
            "resolution": status,
            "candidate_sources": [
                _identity(r) for r in compatible
            ],
            "runtime_verified": False,
        })

        if status == "not_found_in_scanned_manifests" and not optional:
            finding(
                "REFERENCE_NOT_IN_REPOSITORY",
                "Review",
                source,
                f"{kind} '{name}' referenced but not found in scanned manifests",
                evidence,
                "Check Helm/Kustomize rendering, other repositories "
                "and live EKS resources; plan AKS equivalent.",
            )

        elif status == "ambiguous_manifest_candidates":
            finding(
                "AMBIGUOUS_RESOURCE_MATCH",
                "Review",
                source,
                f"Multiple or namespace-uncertain candidates for "
                f"{kind} '{name}'",
                evidence,
                "Resolve active Kustomize overlay/Helm release "
                "and effective namespace.",
            )

    # Duplicate manifest definitions

    groups = defaultdict(list)

    for r in resources:
        if r.get("kind") and r.get("name"):
            groups[
                (
                    r.get("kind"),
                    r.get("name"),
                    r.get("namespace"),
                )
            ].append(r)

    for (kind, name, ns), group in groups.items():
        if len(group) > 1:
            finding(
                "MULTIPLE_MANIFEST_DEFINITIONS",
                "Review",
                group[0],
                f"{len(group)} manifest definitions for "
                f"{kind}/{name} (namespace: {ns or 'unspecified'})",
                ", ".join(
                    x.get("file", "?") for x in group
                ),
                "Determine selected overlay/release and avoid "
                "counting source definitions as deployed instances.",
            )

    for r in resources:
        kind = r.get("kind")

        # ----------------------------------
        # WORKLOAD DEPENDENCIES
        # ----------------------------------

        if kind in WORKLOADS:
            pod = r.get("pod") or {}

            sa = pod.get("serviceAccountName")

            if sa:
                link(
                    r,
                    "ServiceAccount",
                    sa,
                    "uses_service_account",
                    "pod.serviceAccountName",
                )
            else:
                finding(
                    "SERVICE_ACCOUNT_UNSPECIFIED",
                    "Info",
                    r,
                    "No explicit serviceAccountName in manifest",
                    "pod.serviceAccountName absent",
                    "Verify effective ServiceAccount and EKS IRSA; "
                    "assess AKS Workload Identity requirements.",
                )

            # Image pull secrets

            for i, pull in enumerate(
                pod.get("imagePullSecrets") or []
            ):
                if isinstance(pull, dict):
                    link(
                        r,
                        "Secret",
                        pull.get("name"),
                        "uses_image_pull_secret",
                        f"pod.imagePullSecrets[{i}].name",
                    )

            # Volumes

            for i, vol in enumerate(
                pod.get("volumes") or []
            ):
                if not isinstance(vol, dict):
                    continue

                pvc = vol.get("persistentVolumeClaim")

                if isinstance(pvc, dict):
                    link(
                        r,
                        "PersistentVolumeClaim",
                        pvc.get("claimName"),
                        "mounts_pvc",
                        f"pod.volumes[{i}].persistentVolumeClaim.claimName",
                    )

                cm = vol.get("configMap")

                if isinstance(cm, dict):
                    link(
                        r,
                        "ConfigMap",
                        cm.get("name"),
                        "mounts_configmap",
                        f"pod.volumes[{i}].configMap.name",
                        optional=bool(cm.get("optional")),
                    )

                secret = vol.get("secret")

                if isinstance(secret, dict):
                    link(
                        r,
                        "Secret",
                        secret.get("secretName"),
                        "mounts_secret",
                        f"pod.volumes[{i}].secret.secretName",
                        optional=bool(secret.get("optional")),
                    )

                projected = (
                    (vol.get("projected") or {})
                    .get("sources") or []
                )

                for j, p in enumerate(projected):
                    if not isinstance(p, dict):
                        continue

                    for key, rk, field in (
                        ("secret", "Secret", "name"),
                        ("configMap", "ConfigMap", "name"),
                    ):
                        if isinstance(p.get(key), dict):
                            ref = p[key]

                            link(
                                r,
                                rk,
                                ref.get(field),
                                "uses_projected_volume",
                                f"pod.volumes[{i}].projected."
                                f"sources[{j}].{key}.{field}",
                                optional=bool(ref.get("optional")),
                            )

            # Container dependencies

            containers = (
                (r.get("containers") or [])
                + (r.get("initContainers") or [])
            )

            for ci, c in enumerate(containers):
                if not isinstance(c, dict):
                    continue

                for ei, env in enumerate(
                    c.get("env") or []
                ):
                    if not isinstance(env, dict):
                        continue

                    vf = env.get("valueFrom") or {}

                    if isinstance(vf.get("secretKeyRef"), dict):
                        ref = vf["secretKeyRef"]

                        link(
                            r,
                            "Secret",
                            ref.get("name"),
                            "reads_secret_key",
                            f"containers[{ci}].env[{ei}]."
                            f"valueFrom.secretKeyRef "
                            f"(key={ref.get('key')})",
                            optional=bool(ref.get("optional")),
                        )

                    if isinstance(vf.get("configMapKeyRef"), dict):
                        ref = vf["configMapKeyRef"]

                        link(
                            r,
                            "ConfigMap",
                            ref.get("name"),
                            "reads_configmap_key",
                            f"containers[{ci}].env[{ei}]."
                            f"valueFrom.configMapKeyRef "
                            f"(key={ref.get('key')})",
                            optional=bool(ref.get("optional")),
                        )

                for fi, envfrom in enumerate(
                    c.get("envFrom") or []
                ):
                    if not isinstance(envfrom, dict):
                        continue

                    for key, rk in (
                        ("secretRef", "Secret"),
                        ("configMapRef", "ConfigMap"),
                    ):
                        if isinstance(envfrom.get(key), dict):
                            ref = envfrom[key]

                            link(
                                r,
                                rk,
                                ref.get("name"),
                                "imports_environment",
                                f"containers[{ci}].envFrom[{fi}]."
                                f"{key}.name",
                                optional=bool(ref.get("optional")),
                            )

                # Readiness probe

                if not c.get("readinessProbe"):
                    finding(
                        "READINESS_PROBE_NOT_DECLARED",
                        "Review",
                        r,
                        f"Container '{c.get('name')}' "
                        "has no readiness probe",
                        f"container={c.get('name')}",
                        "Assess readiness probes for AKS rollout "
                        "and traffic safety.",
                    )

                # Resource requests

                if (
                    not c.get("cpu_request")
                    or not c.get("memory_request")
                ):
                    finding(
                        "RESOURCE_REQUEST_INCOMPLETE",
                        "Review",
                        r,
                        f"Container '{c.get('name')}' "
                        "lacks CPU or memory request",
                        f"container={c.get('name')}; "
                        f"cpu={c.get('cpu_request')}; "
                        f"memory={c.get('memory_request')}",
                        "Confirm sizing and HPA/VPA assumptions "
                        "against observed EKS usage.",
                    )

            if kind == "StatefulSet":
                for i, claim in enumerate(
                    r.get("volumeClaimTemplates") or []
                ):
                    if isinstance(claim, dict):
                        finding(
                            "STATEFUL_STORAGE_REVIEW",
                            "Review",
                            r,
                            "StatefulSet has volumeClaimTemplates",
                            f"volumeClaimTemplates[{i}]",
                            "Map access modes, storage class, "
                            "reclaim policy, backups and data migration.",
                        )

        # ----------------------------------
        # HPA -> WORKLOAD
        # ----------------------------------

        elif kind == "HorizontalPodAutoscaler":
            target = (
                (r.get("hpa") or {})
                .get("scaleTargetRef") or {}
            )

            if isinstance(target, dict):
                link(
                    r,
                    target.get("kind", "Deployment"),
                    target.get("name"),
                    "scales_workload",
                    "hpa.scaleTargetRef",
                )

        # ----------------------------------
        # INGRESS -> SERVICE
        # ----------------------------------

        elif kind == "Ingress":
            ingress = r.get("ingress") or {}

            for ri, rule in enumerate(
                ingress.get("rules") or []
            ):
                for pi, path in enumerate(
                    rule.get("paths") or []
                ):
                    link(
                        r,
                        "Service",
                        path.get("serviceName"),
                        "routes_to_service",
                        f"ingress.rules[{ri}].paths[{pi}].serviceName",
                    )

            for ti, tls in enumerate(
                ingress.get("tls") or []
            ):
                link(
                    r,
                    "Secret",
                    tls.get("secretName"),
                    "uses_tls_secret",
                    f"ingress.tls[{ti}].secretName",
                )

        # ----------------------------------
        # SERVICE -> WORKLOAD
        # ----------------------------------

        elif kind == "Service":
            svc = r.get("service") or {}
            selector = svc.get("selector") or {}

            if selector:
                matches = []

                for w in resources:
                    if w.get("kind") not in WORKLOADS:
                        continue

                    labels = (
                        (w.get("pod") or {})
                        .get("templateLabels") or {}
                    )

                    if (
                        labels
                        and all(
                            labels.get(k) == v
                            for k, v in selector.items()
                        )
                    ):
                        if (
                            r.get("namespace") is None
                            or w.get("namespace") is None
                            or r.get("namespace")
                            == w.get("namespace")
                        ):
                            matches.append(w)

                if matches:
                    for w in matches:
                        link(
                            r,
                            w["kind"],
                            w.get("name"),
                            "selects_workload_pods",
                            f"service.selector={selector}",
                        )
                else:
                    finding(
                        "SERVICE_SELECTOR_NO_MANIFEST_MATCH",
                        "Review",
                        r,
                        "Service selector does not match any "
                        "discovered workload pod-template labels",
                        f"service.selector={selector}",
                        "Check Helm/Kustomize rendering, "
                        "namespace and pod labels in active deployment.",
                    )

            if svc.get("type") == "LoadBalancer":
                finding(
                    "LOAD_BALANCER_REVIEW",
                    "Review",
                    r,
                    "LoadBalancer Service needs Azure networking review",
                    "service.type=LoadBalancer",
                    "Check internal/external exposure, annotations, "
                    "Azure LB, IP assignment and network policies.",
                )

        # ----------------------------------
        # PVC -> STORAGE CLASS
        # ----------------------------------

        elif kind == "PersistentVolumeClaim":
            pvc = r.get("pvc") or {}
            storage_class = pvc.get("storageClassName")

            if storage_class:
                link(
                    r,
                    "StorageClass",
                    storage_class,
                    "uses_storage_class",
                    "pvc.storageClassName",
                    optional=True,
                )

            finding(
                "PVC_STORAGE_MIGRATION",
                "Review",
                r,
                "PersistentVolumeClaim requires "
                "storage migration assessment",
                f"accessModes={pvc.get('accessModes')}; "
                f"storageClassName={storage_class}",
                "Verify Azure Disk/File mapping, data transfer, "
                "backup/restore and cutover.",
            )

        # ----------------------------------
        # RBAC
        # ----------------------------------

        elif kind in {
            "RoleBinding",
            "ClusterRoleBinding",
        }:
            rb = r.get("rbac") or {}
            role = rb.get("roleRef") or {}

            if isinstance(role, dict):
                link(
                    r,
                    role.get("kind", "Role"),
                    role.get("name"),
                    "binds_role",
                    "rbac.roleRef",
                )

            for i, subject in enumerate(
                rb.get("subjects") or []
            ):
                if (
                    isinstance(subject, dict)
                    and subject.get("kind") == "ServiceAccount"
                ):
                    link(
                        r,
                        "ServiceAccount",
                        subject.get("name"),
                        "grants_permissions_to",
                        f"rbac.subjects[{i}]",
                        target_namespace=(
                            subject.get("namespace")
                            or r.get("namespace")
                        ),
                    )

    counts = Counter(
        r.get("kind", "Unknown")
        for r in resources
    )

    resolution_counts = Counter(
        r["resolution"]
        for r in relationships
    )

    return {
        "dependency_relationships": relationships,
        "migration_findings": findings,
        "assessment_summary": {
            "resources_scanned": len(resources),
            "resource_counts": dict(
                sorted(counts.items())
            ),
            "relationships_discovered": len(relationships),
            "relationship_resolution": dict(
                sorted(resolution_counts.items())
            ),
            "findings_count": len(findings),
            "findings_by_severity": dict(
                sorted(
                    Counter(
                        f["severity"] for f in findings
                    ).items()
                )
            ),
            "assessment_type": "static_repository_analysis",
            "runtime_verified": False,
        },
    }