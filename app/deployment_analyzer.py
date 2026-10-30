from pathlib import Path
from typing import Any
import yaml


WORKLOAD_KINDS = {
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Job",
    "CronJob",
    "Pod",
}

SUPPORTED_KINDS = WORKLOAD_KINDS | {
    "Service",
    "Ingress",
    "HorizontalPodAutoscaler",
    "ConfigMap",
    "Secret",
    "ServiceAccount",
    "PersistentVolumeClaim",
    "PersistentVolume",
    "StorageClass",
    "NetworkPolicy",
    "PodDisruptionBudget",
    "Role",
    "ClusterRole",
    "RoleBinding",
    "ClusterRoleBinding",
    "IngressClass",
    "Gateway",
    "HTTPRoute",
    "ExternalSecret",
    "SecretStore",
    "ClusterSecretStore",
    "ScaledObject",
}

SENSITIVE_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "private_key",
    "apikey",
    "api_key",
    "client_secret",
    "connection_string",
)


def _redact_env(name: str, value: Any) -> Any:
    if any(
        token in name.lower()
        for token in SENSITIVE_TOKENS
    ):
        return "[REDACTED]"

    return value


def _env_vars(container: dict) -> list:
    result = []

    for entry in container.get("env") or []:
        if not isinstance(entry, dict):
            continue

        name = str(entry.get("name") or "")

        if "valueFrom" in entry:
            result.append({
                "name": name,
                "valueFrom": entry.get("valueFrom"),
            })
        else:
            result.append({
                "name": name,
                "value": _redact_env(
                    name,
                    entry.get("value"),
                ),
            })

    return result


def _container_details(container: dict) -> dict:
    resources = container.get("resources") or {}

    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}

    return {
        "name": container.get("name"),
        "image": container.get("image"),
        "imagePullPolicy": container.get(
            "imagePullPolicy"
        ),
        "command": container.get("command"),
        "args": container.get("args"),
        "ports": [
            p.get("containerPort")
            for p in container.get("ports") or []
            if isinstance(p, dict)
        ],
        "cpu_request": requests.get("cpu"),
        "memory_request": requests.get("memory"),
        "cpu_limit": limits.get("cpu"),
        "memory_limit": limits.get("memory"),
        "env": _env_vars(container),
        "envFrom": container.get("envFrom") or [],
        "volumeMounts": container.get(
            "volumeMounts"
        ) or [],
        "livenessProbe": container.get(
            "livenessProbe"
        ),
        "readinessProbe": container.get(
            "readinessProbe"
        ),
        "startupProbe": container.get(
            "startupProbe"
        ),
        "securityContext": container.get(
            "securityContext"
        ),
    }


def _pod_spec(kind: str, spec: dict) -> dict:
    if kind == "Pod":
        return spec

    if kind == "CronJob":
        return (
            (
                (
                    (spec.get("jobTemplate") or {})
                    .get("spec") or {}
                ).get("template") or {}
            ).get("spec") or {}
        )

    return (
        (spec.get("template") or {})
        .get("spec") or {}
    )


def _sanitize_annotations(annotations: Any) -> dict:
    if not isinstance(annotations, dict):
        return {}

    return {
        str(k): (
            "[REDACTED]"
            if any(
                t in str(k).lower()
                for t in SENSITIVE_TOKENS
            )
            else v
        )
        for k, v in annotations.items()
    }


def analyze_deployments(repo_root: Path) -> list[dict]:
    repo_root = Path(repo_root)
    findings = []

    for file in repo_root.rglob("*"):
        if not file.is_file():
            continue

        if file.suffix.lower() not in {
            ".yaml", ".yml"
        }:
            continue

        relative_path = file.relative_to(repo_root)

        if any(
            part in {
                ".git",
                "node_modules",
                ".venv",
                "venv",
            }
            for part in relative_path.parts
        ):
            continue

        try:
            with file.open(
                "r",
                encoding="utf-8",
            ) as stream:
                documents = list(
                    yaml.safe_load_all(stream)
                )
        except (
            OSError,
            UnicodeError,
            yaml.YAMLError,
        ):
            continue

        for doc_index, doc in enumerate(
            documents,
            start=1,
        ):
            if not isinstance(doc, dict):
                continue

            if doc.get("kind") not in SUPPORTED_KINDS:
                continue

            kind = doc["kind"]

            metadata = doc.get("metadata") or {}
            spec = doc.get("spec") or {}

            if (
                not isinstance(metadata, dict)
                or not isinstance(spec, dict)
            ):
                continue

            result = {
                "file": relative_path.as_posix(),
                "document_index": doc_index,
                "apiVersion": doc.get("apiVersion"),
                "kind": kind,
                "name": metadata.get("name"),
                "namespace": metadata.get("namespace"),
                "namespace_status": (
                    "explicit"
                    if metadata.get("namespace")
                    else "unspecified"
                ),
                "labels": metadata.get("labels") or {},
                "annotations": _sanitize_annotations(
                    metadata.get("annotations")
                ),
                "replicas": spec.get("replicas"),
                "containers": [],
            }

            # ----------------------------------
            # WORKLOADS
            # ----------------------------------

            if kind in WORKLOAD_KINDS:
                pod = _pod_spec(kind, spec)

                template = (
                    spec.get("template") or {}
                )

                if kind == "CronJob":
                    template = (
                        (
                            (
                                (spec.get("jobTemplate") or {})
                                .get("spec") or {}
                            ).get("template") or {}
                        )
                    )

                result["pod"] = {
                    "serviceAccountName": pod.get(
                        "serviceAccountName"
                    ),
                    "automountServiceAccountToken": pod.get(
                        "automountServiceAccountToken"
                    ),
                    "imagePullSecrets": pod.get(
                        "imagePullSecrets"
                    ) or [],
                    "volumes": pod.get("volumes") or [],
                    "nodeSelector": pod.get(
                        "nodeSelector"
                    ) or {},
                    "affinity": pod.get("affinity"),
                    "tolerations": pod.get(
                        "tolerations"
                    ) or [],
                    "securityContext": pod.get(
                        "securityContext"
                    ),
                    "hostNetwork": pod.get(
                        "hostNetwork", False
                    ),
                    "dnsPolicy": pod.get(
                        "dnsPolicy"
                    ),
                    "restartPolicy": pod.get(
                        "restartPolicy"
                    ),
                    "templateAnnotations": (
                        _sanitize_annotations(
                            (
                                template.get("metadata")
                                or {}
                            ).get("annotations")
                        )
                    ),
                    "templateLabels": (
                        (
                            template.get("metadata")
                            or {}
                        ).get("labels")
                        or (
                            metadata.get("labels") or {}
                            if kind == "Pod"
                            else {}
                        )
                    ),
                }

                result["containers"] = [
                    _container_details(c)
                    for c in pod.get("containers") or []
                    if isinstance(c, dict)
                ]

                result["initContainers"] = [
                    _container_details(c)
                    for c in pod.get("initContainers") or []
                    if isinstance(c, dict)
                ]

                result["strategy"] = (
                    spec.get("strategy")
                    or spec.get("updateStrategy")
                )

                if kind == "StatefulSet":
                    result["volumeClaimTemplates"] = (
                        spec.get("volumeClaimTemplates") or []
                    )

                if kind in {"Job", "CronJob"}:
                    result["jobSettings"] = {
                        k: spec.get(k)
                        for k in (
                            "schedule",
                            "concurrencyPolicy",
                            "backoffLimit",
                            "ttlSecondsAfterFinished",
                        )
                        if k in spec
                    }

            # ----------------------------------
            # SERVICE
            # ----------------------------------

            elif kind == "Service":
                result["service"] = {
                    "type": spec.get(
                        "type", "ClusterIP"
                    ),
                    "selector": spec.get(
                        "selector"
                    ) or {},
                    "ports": [
                        {
                            "name": p.get("name"),
                            "port": p.get("port"),
                            "targetPort": p.get(
                                "targetPort",
                                p.get("port"),
                            ),
                            "protocol": p.get(
                                "protocol", "TCP"
                            ),
                            "nodePort": p.get(
                                "nodePort"
                            ),
                        }
                        for p in spec.get("ports") or []
                        if isinstance(p, dict)
                    ],
                    "clusterIP": spec.get(
                        "clusterIP"
                    ),
                    "externalName": spec.get(
                        "externalName"
                    ),
                    "loadBalancerClass": spec.get(
                        "loadBalancerClass"
                    ),
                    "loadBalancerSourceRanges": spec.get(
                        "loadBalancerSourceRanges"
                    ),
                }

            # ----------------------------------
            # HPA
            # ----------------------------------

            elif kind == "HorizontalPodAutoscaler":
                result["hpa"] = {
                    "scaleTargetRef": spec.get(
                        "scaleTargetRef"
                    ),
                    "minReplicas": spec.get(
                        "minReplicas", 1
                    ),
                    "maxReplicas": spec.get(
                        "maxReplicas"
                    ),
                    "metrics": spec.get(
                        "metrics"
                    ) or [],
                    "behavior": spec.get(
                        "behavior"
                    ),
                }

            # ----------------------------------
            # INGRESS
            # ----------------------------------

            elif kind == "Ingress":
                rules = []

                for rule in spec.get("rules") or []:
                    if not isinstance(rule, dict):
                        continue

                    paths = []

                    for path in (
                        (rule.get("http") or {})
                        .get("paths") or []
                    ):
                        if not isinstance(path, dict):
                            continue

                        service = (
                            (path.get("backend") or {})
                            .get("service") or {}
                        )

                        paths.append({
                            "path": path.get("path"),
                            "pathType": path.get(
                                "pathType"
                            ),
                            "serviceName": service.get(
                                "name"
                            ),
                            "servicePort": service.get(
                                "port"
                            ),
                        })

                    rules.append({
                        "host": rule.get("host"),
                        "paths": paths,
                    })

                result["ingress"] = {
                    "ingressClassName": spec.get(
                        "ingressClassName"
                    ),
                    "rules": rules,
                    "tls": [
                        {
                            "hosts": t.get("hosts") or [],
                            "secretName": t.get(
                                "secretName"
                            ),
                        }
                        for t in spec.get("tls") or []
                        if isinstance(t, dict)
                    ],
                    "defaultBackend": spec.get(
                        "defaultBackend"
                    ),
                }

            # ----------------------------------
            # CONFIGMAP
            # ----------------------------------

            
            elif kind == "ConfigMap":
                config_data = doc.get("data") or {}

                result["configMap"] = {
                    "keys": sorted(config_data.keys()),
                    "binaryKeys": sorted(
                        (doc.get("binaryData") or {}).keys()
                    ),
                    "database_endpoints": {
                        key: value
                        for key, value in config_data.items()
                        if (
                            key.upper() in {
                                "SPRING_DATASOURCE_URL",
                                "DATABASE_URL",
                                "JDBC_URL",
                            }
                            and isinstance(value, str)
                            and value.startswith("jdbc:")
                            and "://" in value
                            and "@" not in value.split("://", 1)[1].split("/", 1)[0]
                            and "?" not in value
                            and "#" not in value
                        )
                    },
                }


            # ----------------------------------
            # SECRET (NO VALUES)
            # ----------------------------------

            elif kind == "Secret":
                result["secret"] = {
                    "type": doc.get("type"),
                    "keys": sorted(
                        set(
                            (doc.get("data") or {}).keys()
                        )
                        | set(
                            (doc.get("stringData") or {}).keys()
                        )
                    ),
                }

            # ----------------------------------
            # SERVICE ACCOUNT
            # ----------------------------------

            elif kind == "ServiceAccount":
                result["serviceAccount"] = {
                    "imagePullSecrets": doc.get(
                        "imagePullSecrets"
                    ) or [],
                    "automountServiceAccountToken": doc.get(
                        "automountServiceAccountToken"
                    ),
                }

            # ----------------------------------
            # PVC
            # ----------------------------------

            elif kind == "PersistentVolumeClaim":
                result["pvc"] = {
                    "storageClassName": spec.get(
                        "storageClassName"
                    ),
                    "accessModes": spec.get(
                        "accessModes"
                    ) or [],
                    "resources": spec.get(
                        "resources"
                    ) or {},
                    "volumeName": spec.get(
                        "volumeName"
                    ),
                }

            # ----------------------------------
            # PV
            # ----------------------------------

            elif kind == "PersistentVolume":
                result["pv"] = {
                    "storageClassName": spec.get(
                        "storageClassName"
                    ),
                    "capacity": spec.get(
                        "capacity"
                    ),
                    "accessModes": spec.get(
                        "accessModes"
                    ),
                    "reclaimPolicy": spec.get(
                        "persistentVolumeReclaimPolicy"
                    ),
                    "volumeSourceTypes": [
                        k for k in spec
                        if k not in {
                            "capacity",
                            "accessModes",
                            "persistentVolumeReclaimPolicy",
                            "storageClassName",
                            "claimRef",
                            "mountOptions",
                            "volumeMode",
                            "nodeAffinity",
                        }
                    ],
                }

            # ----------------------------------
            # STORAGE CLASS
            # ----------------------------------

            elif kind == "StorageClass":
                result["storageClass"] = {
                    "provisioner": doc.get(
                        "provisioner"
                    ),
                    "reclaimPolicy": doc.get(
                        "reclaimPolicy"
                    ),
                    "volumeBindingMode": doc.get(
                        "volumeBindingMode"
                    ),
                    "allowVolumeExpansion": doc.get(
                        "allowVolumeExpansion"
                    ),
                }

            # ----------------------------------
            # RBAC
            # ----------------------------------

            elif kind in {"Role", "ClusterRole"}:
                result["rbac"] = {
                    "rules": doc.get("rules") or []
                }

            elif kind in {
                "RoleBinding",
                "ClusterRoleBinding",
            }:
                result["rbac"] = {
                    "roleRef": doc.get("roleRef"),
                    "subjects": doc.get(
                        "subjects"
                    ) or [],
                }

            # ----------------------------------
            # OTHER RESOURCE TYPES
            # ----------------------------------

            else:
                result["configuration_fields"] = sorted(
                    spec.keys()
                )

            findings.append(result)

    return findings