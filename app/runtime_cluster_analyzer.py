"""Read-only Kubernetes runtime inventory for migration assessment.

Run locally with a configured kubeconfig. Never reads Secret data, Pod logs,
executes commands inside Pods, or changes Kubernetes resources.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _names(items: Any) -> list[str]:
    return sorted({x.name for x in (items or []) if getattr(x, 'name', None)})


def collect_runtime_snapshot(*, context: str, namespace: str, kubeconfig: str | None = None) -> dict[str, Any]:
    """Collect read-only evidence for one explicit namespace and kubeconfig context.

    Requires: pip install kubernetes
    The current kubeconfig user must have list/get permissions for resources.
    """
    if not context or not namespace or namespace == '*':
        raise ValueError('Explicit kubeconfig context and namespace are required')
    try:
        from kubernetes import client, config
        from kubernetes.client.exceptions import ApiException
    except ImportError as exc:
        raise RuntimeError('Install the Kubernetes Python client: pip install kubernetes') from exc

    contexts, active = config.list_kube_config_contexts(config_file=kubeconfig)
    known = {c['name'] for c in (contexts or [])}
    if context not in known:
        raise ValueError(f'Kubeconfig context not found: {context}')
    config.load_kube_config(config_file=kubeconfig, context=context)
    core = client.CoreV1Api()
    apps = client.AppsV1Api()
    autoscaling = client.AutoscalingV2Api()

    output: dict[str, Any] = {
        'context': context, 'namespace': namespace,
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'source': 'KUBERNETES_API_READ_ONLY', 'runtime_verified': False,
        'resources': {}, 'warnings': [],
    }

    def collect(kind: str, action, transform):
        try:
            output['resources'][kind] = [transform(x) for x in action().items]
        except ApiException as exc:
            output['resources'][kind] = []
            output['warnings'].append(f'{kind}: Kubernetes API returned HTTP {exc.status}; no data collected')
        except Exception as exc:
            output['resources'][kind] = []
            output['warnings'].append(f'{kind}: {type(exc).__name__}: {exc}')

    collect('deployments', lambda: apps.list_namespaced_deployment(namespace), lambda x: {
        'name': x.metadata.name, 'namespace': x.metadata.namespace,
        'labels': x.metadata.labels or {},
        'replicas_desired': x.spec.replicas,
        'replicas_ready': (x.status.ready_replicas or 0),
        'images': [c.image for c in x.spec.template.spec.containers],
        'service_account': x.spec.template.spec.service_account_name,
        'configmap_refs': sorted({r.name for c in x.spec.template.spec.containers for r in (c.env_from or []) if r.config_map_ref and r.config_map_ref.name}),
        'secret_refs': sorted({r.name for c in x.spec.template.spec.containers for r in (c.env_from or []) if r.secret_ref and r.secret_ref.name}),
        'pvc_refs': sorted({v.persistent_volume_claim.claim_name for v in (x.spec.template.spec.volumes or []) if v.persistent_volume_claim}),
    })
    collect('services', lambda: core.list_namespaced_service(namespace), lambda x: {
        'name': x.metadata.name, 'namespace': x.metadata.namespace,
        'type': x.spec.type, 'selector': x.spec.selector or {},
        'ports': [{'port': p.port, 'target_port': str(p.target_port), 'protocol': p.protocol} for p in (x.spec.ports or [])],
    })
    collect('pods', lambda: core.list_namespaced_pod(namespace), lambda x: {
        'name': x.metadata.name, 'phase': x.status.phase,
        'node': x.spec.node_name, 'restart_count': sum(s.restart_count or 0 for s in (x.status.container_statuses or [])),
        'owner_references': [{'kind': r.kind, 'name': r.name} for r in (x.metadata.owner_references or [])],
    })
    collect('hpas', lambda: autoscaling.list_namespaced_horizontal_pod_autoscaler(namespace), lambda x: {
        'name': x.metadata.name, 'min_replicas': x.spec.min_replicas,
        'max_replicas': x.spec.max_replicas,
        'target_kind': x.spec.scale_target_ref.kind,
        'target_name': x.spec.scale_target_ref.name,
    })
    collect('pvcs', lambda: core.list_namespaced_persistent_volume_claim(namespace), lambda x: {
        'name': x.metadata.name, 'phase': x.status.phase if x.status else None,
        'storage_class': x.spec.storage_class_name,
        'requested_storage': str((x.spec.resources.requests or {}).get('storage', '')),
    })
    collect('serviceaccounts', lambda: core.list_namespaced_service_account(namespace), lambda x: {
        'name': x.metadata.name,
        'annotations': {k: v for k, v in (x.metadata.annotations or {}).items()
                        if k.startswith('eks.amazonaws.com/') or k.startswith('azure.workload.identity/')},
    })
    collect('configmaps', lambda: core.list_namespaced_config_map(namespace), lambda x: {
        'name': x.metadata.name, 'keys': sorted((x.data or {}).keys()),
    })
    collect('secrets', lambda: core.list_namespaced_secret(namespace), lambda x: {
        'name': x.metadata.name, 'type': x.type,
        # Deliberately do not access x.data or x.string_data.
    })

    output['runtime_verified'] = bool(output['resources'].get('deployments') is not None and
                                      not any(w.startswith('deployments:') for w in output['warnings']))
    output['verification_scope'] = 'NAMESPACE_RESOURCE_INVENTORY_ONLY'
    output['source_manifest_provenance_verified'] = False
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description='Read-only Kubernetes namespace inventory')
    parser.add_argument('--context', required=True, help='Exact kubeconfig context')
    parser.add_argument('--namespace', required=True, help='Namespace to inspect')
    parser.add_argument('--kubeconfig', help='Optional kubeconfig path')
    parser.add_argument('--output', default='runtime-snapshot.json', help='Output JSON file')
    args = parser.parse_args()
    result = collect_runtime_snapshot(context=args.context, namespace=args.namespace, kubeconfig=args.kubeconfig)
    destination = Path(args.output)
    destination.write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(f'Saved read-only snapshot to {destination}; warnings={len(result["warnings"])}')


if __name__ == '__main__':
    main()
