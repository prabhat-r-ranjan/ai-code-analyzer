"""Read-only, namespace-scoped Kubernetes runtime evidence for migration assessment.

Requires ``pip install kubernetes`` and a configured kubeconfig. Does not
retrieve Secret values, ConfigMap values, logs, or execute or modify workloads.
No exact Git-to-runtime provenance is claimed. Target existence is checked by
namespace inventory names only; no connectivity or key existence is verified.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _name(obj: Any) -> str | None:
    return getattr(obj, 'name', None) if obj is not None else None


def _sorted_names(values: Any) -> list[str]:
    return sorted({v for v in values if v})


def _pod_dependencies(pod_spec: Any) -> dict[str, Any]:
    """Extract named references only; never read configuration or secret values."""
    configmaps: set[str] = set()
    secrets: set[str] = set()
    pvcs: set[str] = set()
    references: list[dict[str, str]] = []

    def add(kind: str, name: str | None, via: str, optional: bool | None = None) -> None:
        if not name:
            return
        if kind == 'ConfigMap':
            configmaps.add(name)
        elif kind == 'Secret':
            secrets.add(name)
        elif kind == 'PersistentVolumeClaim':
            pvcs.add(name)
        references.append({'kind': kind, 'name': name, 'via': via, 'optional': optional})

    containers = list(getattr(pod_spec, 'init_containers', None) or []) + list(getattr(pod_spec, 'containers', None) or [])
    for container in containers:
        prefix = f'container/{container.name}'
        for source in container.env_from or []:
            if source.config_map_ref:
                add('ConfigMap', _name(source.config_map_ref), prefix + '/envFrom', getattr(source.config_map_ref, 'optional', None))
            if source.secret_ref:
                add('Secret', _name(source.secret_ref), prefix + '/envFrom', getattr(source.secret_ref, 'optional', None))
        for env in container.env or []:
            source = env.value_from
            if not source:
                continue
            if source.config_map_key_ref:
                add('ConfigMap', _name(source.config_map_key_ref), prefix + f'/env/{env.name}', getattr(source.config_map_key_ref, 'optional', None))
            if source.secret_key_ref:
                add('Secret', _name(source.secret_key_ref), prefix + f'/env/{env.name}', getattr(source.secret_key_ref, 'optional', None))

    for volume in pod_spec.volumes or []:
        via = f'volume/{volume.name}'
        if volume.config_map:
            add('ConfigMap', _name(volume.config_map), via, getattr(volume.config_map, 'optional', None))
        if volume.secret:
            add('Secret', getattr(volume.secret, 'secret_name', None), via, getattr(volume.secret, 'optional', None))
        if volume.persistent_volume_claim:
            add('PersistentVolumeClaim', getattr(volume.persistent_volume_claim, 'claim_name', None), via)
        if volume.projected:
            for source in volume.projected.sources or []:
                if source.config_map:
                    add('ConfigMap', _name(source.config_map), via + '/projected', getattr(source.config_map, 'optional', None))
                if source.secret:
                    add('Secret', _name(source.secret), via + '/projected', getattr(source.secret, 'optional', None))
                # serviceAccountToken/downwardAPI are intentionally not Secrets.
        if volume.csi and volume.csi.node_publish_secret_ref:
            add('Secret', _name(volume.csi.node_publish_secret_ref), via + '/csi')

    for pull_secret in pod_spec.image_pull_secrets or []:
        add('Secret', _name(pull_secret), 'imagePullSecrets')

    return {
        'configmap_refs': sorted(configmaps),
        'secret_refs': sorted(secrets),
        'pvc_refs': sorted(pvcs),
        'dependency_references': [
            {'kind': kind, 'name': name, 'via': via,
             'optional': optional, 'evidence': 'KUBERNETES_POD_SPEC'}
            for kind, name, via, optional in sorted(
                {(r['kind'], r['name'], r['via'], r['optional']) for r in references},
                key=lambda r: (r[0], r[1], r[2], str(r[3]))
            )
        ],
    }


def _workload(obj: Any, kind: str) -> dict[str, Any]:
    template = obj.spec.template
    pod_spec = template.spec
    status = obj.status
    result = {
        'name': obj.metadata.name,
        'namespace': obj.metadata.namespace,
        'kind': kind,
        'labels': obj.metadata.labels or {},
        'pod_labels': template.metadata.labels or {},
        'replicas_desired': getattr(obj.spec, 'replicas', None),
        'replicas_ready': getattr(status, 'ready_replicas', None) or 0,
        'images': [c.image for c in (pod_spec.init_containers or []) + (pod_spec.containers or [])],
        'service_account': pod_spec.service_account_name or 'default',
        **_pod_dependencies(pod_spec),
    }
    if kind == 'DaemonSet':
        result['replicas_desired'] = status.desired_number_scheduled or 0
        result['replicas_ready'] = status.number_ready or 0
    return result


def _pod(obj: Any) -> dict[str, Any]:
    statuses = (obj.status.init_container_statuses or []) + (obj.status.container_statuses or [])
    return {
        'name': obj.metadata.name,
        'namespace': obj.metadata.namespace,
        'labels': obj.metadata.labels or {},
        'phase': obj.status.phase,
        'node': obj.spec.node_name,
        'containers_ready': sum(bool(s.ready) for s in statuses),
        'containers_total': len(statuses),
        'restart_count': sum(s.restart_count or 0 for s in statuses),
        'owner_references': [{'kind': r.kind, 'name': r.name} for r in (obj.metadata.owner_references or [])],
        'service_account': obj.spec.service_account_name or 'default',
        **_pod_dependencies(obj.spec),
    }


def _service(obj: Any) -> dict[str, Any]:
    return {
        'name': obj.metadata.name,
        'namespace': obj.metadata.namespace,
        'type': obj.spec.type,
        'selector': obj.spec.selector or {},
        'ports': [
            {'port': p.port, 'target_port': str(p.target_port) if p.target_port is not None else None,
             'protocol': p.protocol}
            for p in (obj.spec.ports or [])
        ],
    }


def _service_pod_matches(resources: dict[str, Any]) -> list[dict[str, Any]]:
    """Selector evidence, not network connectivity or EndpointSlice readiness."""
    pods = resources.get('pods', [])
    result = []
    for service in resources.get('services', []):
        selector = service['selector']
        if not selector:
            result.append({'service': service['name'], 'matched_pods': [], 'evidence': 'NO_SELECTOR',
                           'note': 'Selectorless Service: cannot infer backing Pods from labels'})
            continue
        matched = sorted(p['name'] for p in pods if all(p['labels'].get(k) == v for k, v in selector.items()))
        result.append({'service': service['name'], 'matched_pods': matched,
                       'evidence': 'SERVICE_SELECTOR_MATCH',
                       'note': 'Label match only; EndpointSlice and traffic health not verified'})
    return result



def _validate_dependency_targets(resources: dict[str, Any], successful: set[str]) -> dict[str, int]:
    """Check names against successfully listed namespace inventories only.

    Secret existence remains NOT_VERIFIED: Secret API calls are deliberately avoided.
    This checks name existence, not configuration keys, readiness, or successful use.
    """
    collections = {
        'ConfigMap': 'configmaps',
        'Secret': 'secrets',
        'PersistentVolumeClaim': 'pvcs',
    }
    known = {
        kind: {item['name'] for item in resources.get(collection, [])}
        for kind, collection in collections.items()
        if collection in successful
    }
    counts = {'TARGET_EXISTS': 0, 'TARGET_NOT_FOUND': 0, 'NOT_VERIFIED': 0}
    for collection in ('deployments', 'statefulsets', 'daemonsets', 'pods'):
        if collection not in successful:
            continue
        for workload in resources.get(collection, []):
            for reference in workload.get('dependency_references', []):
                kind = reference['kind']
                if kind not in known:
                    status = 'NOT_VERIFIED'
                elif reference['name'] in known[kind]:
                    status = 'TARGET_EXISTS'
                else:
                    status = 'TARGET_NOT_FOUND'
                reference['target_status'] = status
                reference['target_evidence'] = (
                    'NAMESPACE_RESOURCE_NAME_INVENTORY' if status != 'NOT_VERIFIED'
                    else 'TARGET_INVENTORY_UNAVAILABLE_OR_NOT_COLLECTED'
                )
                counts[status] += 1
    return counts


def collect_runtime_snapshot(*, context: str, namespace: str, kubeconfig: str | None = None) -> dict[str, Any]:
    """Collect read-only evidence for one explicit kubeconfig context and namespace."""
    if not context or not context.strip() or not namespace or not namespace.strip() or namespace.strip() == '*':
        raise ValueError('Explicit kubeconfig context and namespace are required')
    try:
        from kubernetes import client, config
        from kubernetes.client.exceptions import ApiException
    except ImportError as exc:
        raise RuntimeError('Install the Kubernetes Python client: pip install kubernetes') from exc

    contexts, _ = config.list_kube_config_contexts(config_file=kubeconfig)
    if context not in {c['name'] for c in (contexts or [])}:
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
    successful: set[str] = set()

    def collect(kind: str, action: Any, transform: Any) -> None:
        try:
            output['resources'][kind] = [transform(item) for item in action().items]
            successful.add(kind)
        except ApiException as exc:
            output['resources'][kind] = []
            output['warnings'].append(f'{kind}: Kubernetes API HTTP {exc.status}; data unavailable')
        except Exception as exc:
            output['resources'][kind] = []
            output['warnings'].append(f'{kind}: {type(exc).__name__}: collection failed')

    collect('deployments', lambda: apps.list_namespaced_deployment(namespace), lambda x: _workload(x, 'Deployment'))
    collect('statefulsets', lambda: apps.list_namespaced_stateful_set(namespace), lambda x: _workload(x, 'StatefulSet'))
    collect('daemonsets', lambda: apps.list_namespaced_daemon_set(namespace), lambda x: _workload(x, 'DaemonSet'))
    collect('services', lambda: core.list_namespaced_service(namespace), _service)
    collect('pods', lambda: core.list_namespaced_pod(namespace), _pod)
    collect('hpas', lambda: autoscaling.list_namespaced_horizontal_pod_autoscaler(namespace), lambda x: {
        'name': x.metadata.name, 'min_replicas': x.spec.min_replicas,
        'max_replicas': x.spec.max_replicas,
        'target_kind': x.spec.scale_target_ref.kind, 'target_name': x.spec.scale_target_ref.name,
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
    # ConfigMap list responses include values; never serialize or inspect those values.
    collect('configmaps', lambda: core.list_namespaced_config_map(namespace), lambda x: {
        'name': x.metadata.name, 'keys': sorted((x.data or {}).keys()),
    })
    # Secret metadata only: request partial object metadata, not full Secret objects.
    # Avoid list_namespaced_secret, which would download sensitive values even if ignored.
    # Secret names referenced by Pod specs remain available above.
    output['resources']['secrets'] = []
    output['warnings'].append('secrets: omitted intentionally; Secret objects are not fetched (references remain available)')

    if 'services' in successful and 'pods' in successful:
        output['service_pod_mappings'] = _service_pod_matches(output['resources'])
    else:
        output['service_pod_mappings'] = []
        output['warnings'].append('service_pod_mappings: unavailable because Services or Pods could not be listed')

    output['dependency_target_summary'] = _validate_dependency_targets(output['resources'], successful)
    output['runtime_verified'] = 'deployments' in successful and 'pods' in successful
    output['verification_scope'] = 'NAMESPACE_RESOURCE_INVENTORY_DECLARED_DEPENDENCIES_AND_NAME_EXISTENCE'
    output['source_manifest_provenance_verified'] = False
    output['collection_status'] = {k: ('SUCCESS' if k in successful else 'UNAVAILABLE') for k in (
        'deployments', 'statefulsets', 'daemonsets', 'services', 'pods', 'hpas', 'pvcs', 'serviceaccounts', 'configmaps'
    )}
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description='Read-only Kubernetes namespace runtime assessment')
    parser.add_argument('--context', required=True, help='Exact kubeconfig context')
    parser.add_argument('--namespace', required=True, help='Exact namespace')
    parser.add_argument('--kubeconfig', help='Optional kubeconfig path')
    parser.add_argument('--output', default='runtime-snapshot.json', help='Output JSON file')
    args = parser.parse_args()
    result = collect_runtime_snapshot(context=args.context, namespace=args.namespace, kubeconfig=args.kubeconfig)
    destination = Path(args.output)
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Saved read-only snapshot to {destination}; warnings={len(result["warnings"])}')


if __name__ == '__main__':
    main()
