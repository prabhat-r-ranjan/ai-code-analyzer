"""Select one application workload from a namespace inventory without asserting Git provenance."""
from __future__ import annotations
from copy import deepcopy


def select_runtime_workload(snapshot: dict, workload_name: str) -> dict:
    name = workload_name.strip()
    if not name:
        raise ValueError('runtime_workload must not be empty')
    result = deepcopy(snapshot)
    resources = result.get('resources') or {}
    kinds = ('deployments', 'statefulsets', 'daemonsets')
    matches = [(group, item) for group in kinds for item in resources.get(group, [])
               if item.get('name') == name]
    if len(matches) != 1:
        for group in kinds:
            result['resources'][group] = []
        result['resources']['pods'] = []
        result['resources']['services'] = []
        result['resources']['hpas'] = []
        result['resources']['pvcs'] = []
        result['resources']['serviceaccounts'] = []
        result['resources']['configmaps'] = []
        result['service_pod_mappings'] = []
        result['runtime_verified'] = False
        result['application_scope'] = {
            'requested_workload': name,
            'status': 'NOT_FOUND_IN_SCANNED_NAMESPACE' if not matches else 'AMBIGUOUS_WORKLOAD',
            'matched_workloads': len(matches),
            'source_to_runtime_provenance_verified': False,
        }
        return result

    group, workload = matches[0]
    labels = workload.get('pod_labels') or {}
    # Exact controller->Pod ownership isn't always available (Deployment -> ReplicaSet -> Pod).
    # Label matches are candidates, not verified ownership.
    pods = [p for p in resources.get('pods', []) if labels and
            all(p.get('labels', {}).get(k) == v for k, v in labels.items())]
    pod_names = {p['name'] for p in pods}
    services = [s for s in resources.get('services', []) if s.get('selector') and
                any(all(p.get('labels', {}).get(k) == v for k, v in s['selector'].items()) for p in pods)]
    for key in kinds:
        result['resources'][key] = [workload] if key == group else []
    result['resources']['pods'] = pods
    result['resources']['services'] = services
    result['resources']['hpas'] = [h for h in resources.get('hpas', [])
                                   if h.get('target_name') == name and h.get('target_kind') == workload.get('kind')]
    # Referenced resources are retained as inventory evidence, not exported as dependencies.
    referenced_pvcs = set(workload.get('pvc_refs') or [])
    referenced_pvcs.update(ref for p in pods for ref in p.get('pvc_refs') or [])
    result['resources']['pvcs'] = [v for v in resources.get('pvcs', []) if v.get('name') in referenced_pvcs]
    result['resources']['serviceaccounts'] = [v for v in resources.get('serviceaccounts', [])
                                               if v.get('name') == workload.get('service_account')]
    referenced_configmaps = set(workload.get('configmap_refs') or [])
    referenced_configmaps.update(ref for p in pods for ref in p.get('configmap_refs') or [])
    result['resources']['configmaps'] = [v for v in resources.get('configmaps', [])
                                         if v.get('name') in referenced_configmaps]
    result['service_pod_mappings'] = [m for m in result.get('service_pod_mappings', [])
                                      if m.get('service') in {s['name'] for s in services}]
    result['application_scope'] = {
        'requested_workload': name, 'status': 'WORKLOAD_FOUND',
        'matched_kind': workload.get('kind'), 'matched_pods_by_labels': len(pods),
        'pod_matching_evidence': 'POD_TEMPLATE_LABEL_MATCH_CANDIDATE',
        'source_to_runtime_provenance_verified': False,
    }
    result['source_manifest_provenance_verified'] = False
    return result
