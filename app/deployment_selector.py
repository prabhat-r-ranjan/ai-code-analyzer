"""Static, evidence-based deployment manifest selection for a single repository.

Does not claim that a manifest is running in a Kubernetes cluster.
No shell commands, Helm templates, or Kustomize plugins are executed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
import yaml

SKIP = {'.git', '.venv', 'venv', 'node_modules', 'target', 'build', '__pycache__'}
KUSTOMIZE = {'kustomization.yaml', 'kustomization.yml', 'Kustomization'}
WORKFLOWS = {'Jenkinsfile', 'azure-pipelines.yml', 'azure-pipelines.yaml', '.gitlab-ci.yml', 'cloudbuild.yaml'}


def _path(root: Path, base: Path, value: str) -> Path | None:
    """Only permit paths inside cloned repository; no traversal outside root."""
    if not value or '${' in value or '$(' in value or '{{' in value or '*' in value:
        return None
    candidate = (base / value).resolve()
    return candidate if candidate.is_relative_to(root.resolve()) else None


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _yaml(path: Path) -> list[dict]:
    try:
        with path.open(encoding='utf-8') as f:
            return [d for d in yaml.safe_load_all(f) if isinstance(d, dict)]
    except (OSError, UnicodeError, yaml.YAMLError):
        return []


def _source_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*') if p.is_file() and not any(part in SKIP for part in p.relative_to(root).parts))


def _resolve_kustomize(root: Path, directory: Path, visited: set[Path] | None = None) -> tuple[set[str], list[str]]:
    visited = visited or set()
    directory = directory.resolve()
    if directory in visited:
        return set(), [f'Kustomize cycle at {_rel(root, directory)}']
    visited.add(directory)
    config = next((directory / n for n in KUSTOMIZE if (directory / n).is_file()), None)
    if not config:
        return set(), [f'No kustomization file in {_rel(root, directory)}']
    docs = _yaml(config)
    if not docs:
        return set(), [f'Invalid Kustomize file {_rel(root, config)}']
    doc = docs[0]
    selected: set[str] = set()
    warnings: list[str] = []
    for field in ('resources', 'bases', 'components'):
        for item in doc.get(field) or []:
            if not isinstance(item, str):
                continue
            target = _path(root, directory, item)
            if target is None:
                warnings.append(f'Unresolved {field} reference: {item}')
            elif target.is_dir():
                found, issues = _resolve_kustomize(root, target, visited)
                selected.update(found)
                warnings.extend(issues)
            elif target.is_file():
                selected.add(_rel(root, target))
            else:
                warnings.append(f'Missing {field}: {item}')
    # Patches and generators influence effective configuration; include as evidence, not rendered resources.
    for item in doc.get('patchesStrategicMerge') or []:
        target = _path(root, directory, item) if isinstance(item, str) else None
        if target and target.is_file():
            warnings.append(f'Patch requires effective render: {_rel(root, target)}')
    for item in doc.get('patches') or []:
        if isinstance(item, dict) and item.get('path'):
            warnings.append(f'Patch requires effective render: {item["path"]}')
    if doc.get('helmCharts') or doc.get('generators') or doc.get('transformers'):
        warnings.append('Kustomize generator/Helm rendering not evaluated')
    return selected, warnings


def _resolve_raw(root: Path, base: Path, value: str) -> tuple[set[str], list[str]]:
    target = _path(root, base, value)
    if target is None:
        return set(), [f'Dynamic or external path: {value}']
    if target.is_file():
        if target.name in KUSTOMIZE:
            return _resolve_kustomize(root, target.parent)
        return {_rel(root, target)}, []
    if target.is_dir():
        return { _rel(root, p) for p in target.rglob('*') if p.is_file() and p.suffix.lower() in {'.yml', '.yaml'} and not any(part in SKIP for part in p.relative_to(root).parts) }, []
    return set(), [f'Missing path: {value}']


def discover_deployment_entrypoints(repo_root: Path) -> list[dict[str, Any]]:
    """Find explicit deployment references without executing repository content."""
    root = Path(repo_root).resolve()
    entries: list[dict[str, Any]] = []
    for file in _source_files(root):
        rel = _rel(root, file)
        is_ci = (file.name in WORKFLOWS or rel.startswith('.github/workflows/')
                 or file.name.lower().startswith('jenkinsfile'))
        if is_ci:
            try:
                content = file.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                continue
            lines = content.splitlines()
            # Join shell lines ending in backslash; keep original starting line number.
            logical: list[tuple[int, str]] = []
            pending = ''
            start = 1
            for lineno, line in enumerate(lines, 1):
                part = line.strip()
                if not pending:
                    start = lineno
                pending += ' ' + part.rstrip('\\').strip()
                if part.endswith('\\'):
                    continue
                logical.append((start, pending.strip()))
                pending = ''
            if pending:
                logical.append((start, pending.strip()))

            for lineno, cleaned in logical:
                # Explicit kubectl apply/replace/create references.
                if re.search(r'\bkubectl(?:\s+--?[\w=-]+)*\s+(?:apply|replace|create)\b', cleaned):
                    for match in re.finditer(
                        r'(?<![\w-])(--filename|--kustomize|-f|-k)(?:\s+|=)([^\s;|&]+)',
                        cleaned
                    ):
                        flag, value = match.groups()
                        entries.append({
                            'type': 'kustomize' if flag in ('-k', '--kustomize') else 'raw',
                            'source_file': rel, 'line': lineno,
                            'path': value.strip('"\' '), 'environment': None,
                            'evidence': cleaned[:500]
                        })
                # azure/k8s-deploy GitHub Action: manifests: k8s/deployment.yaml
                if rel.startswith('.github/workflows/'):
                    match = re.search(r'^\s*manifests\s*:\s*(\S[^#]*)', cleaned)
                    if match and not match.group(1).strip().startswith(('|', '>')):
                        value = match.group(1).strip().strip('"\'')
                        if value:
                            entries.append({
                                'type': 'raw', 'source_file': rel, 'line': lineno,
                                'path': value, 'environment': None,
                                'evidence': cleaned[:500]
                            })
            if re.search(r'\bhelm\s+(?:upgrade|install|template)\b', content):
                entries.append({
                    'type': 'helm', 'source_file': rel, 'line': None,
                    'path': None, 'environment': None,
                    'evidence': 'Helm command found; chart/values rendering requires further resolution'
                })
        if file.suffix.lower() in {'.yaml', '.yml'}:
            for doc in _yaml(file):
                if doc.get('kind') != 'Application' or not str(doc.get('apiVersion', '')).startswith('argoproj.io/'):
                    continue
                source = (doc.get('spec') or {}).get('source') or {}
                sources = (doc.get('spec') or {}).get('sources') or [source]
                for item in sources:
                    if not isinstance(item, dict):
                        continue
                    entries.append({
                        'type': 'argocd', 'source_file': rel, 'line': None,
                        'path': item.get('path'), 'repo_url': item.get('repoURL'),
                        'chart': item.get('chart'),
                        'environment': (doc.get('metadata') or {}).get('name'),
                        'evidence': 'Argo CD Application source declaration'
                    })
    return entries


def resolve_selected_manifests(repo_root: Path, entrypoints: list[dict]) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    selections: list[dict] = []
    warnings: list[str] = []
    if not entrypoints:
        warnings.append(
            'NO_DEPLOYMENT_ENTRYPOINT_FOUND: No supported CI/CD or Argo CD deployment '
            'reference was detected in this repository. Manifests remain candidates; '
            'deployment may be configured externally or use unsupported syntax.'
        )
    for entry in entrypoints:
        kind = entry['type']
        path = entry.get('path')
        source = root / entry['source_file']
        selected: set[str] = set()
        issues: list[str] = []
        if kind in {'raw', 'kustomize'} and path:
            # CI commands usually run from repository root; working-directory overrides require manual validation.
            if kind == 'kustomize':
                target = _path(root, root, path)
                if target and target.is_dir():
                    selected, issues = _resolve_kustomize(root, target)
                else:
                    issues = [f'Unresolved Kustomize directory: {path}']
            else:
                selected, issues = _resolve_raw(root, root, path)
        elif kind == 'argocd':
            repo_url = entry.get('repo_url')
            if repo_url and repo_url not in ('.', 'file://.'):
                issues = [f'Argo CD source repository must be verified as this clone: {repo_url}']
            elif path:
                target = _path(root, root, path)
                if target and target.is_dir():
                    if any((target / n).is_file() for n in KUSTOMIZE):
                        selected, issues = _resolve_kustomize(root, target)
                    elif (target / 'Chart.yaml').is_file():
                        issues = ['Helm chart rendering not performed']
                    else:
                        selected, issues = _resolve_raw(root, root, path)
                else:
                    issues = [f'Unresolved Argo CD path: {path}']
            else:
                issues = ['Argo CD chart/path not resolved']
        else:
            issues = ['Helm chart and values rendering not performed']
        selections.append({**entry, 'selected_files': sorted(selected), 'warnings': issues, 'runtime_verified': False})
        warnings.extend(f"{entry['source_file']}: {msg}" for msg in issues)
    return {'entrypoints': selections, 'warnings': warnings, 'runtime_verified': False}


def classify_manifest_candidates(resources: list[dict], selections: dict) -> list[dict]:
    """Classify source manifests; never promote a candidate to live-active."""
    selected_by: dict[str, list[str]] = {}
    for entry in selections.get('entrypoints') or []:
        for file in entry.get('selected_files') or []:
            selected_by.setdefault(file, []).append(entry['source_file'])
    results = []
    for resource in resources:
        source = resource.get('file') or resource.get('source_file')
        evidence = selected_by.get(source, [])
        results.append({'kind': resource.get('kind'), 'name': resource.get('name'), 'namespace': resource.get('namespace'), 'source_file': source, 'document_index': resource.get('document_index'), 'selection_status': 'SELECTED_BY_SOURCE' if evidence else 'CANDIDATE_ONLY', 'selected_by': sorted(set(evidence)), 'runtime_verified': False})
    return results


def build_deployment_selection_report(resources: list[dict], selections: dict) -> dict:
    classified = classify_manifest_candidates(resources, selections)
    grouped: dict[tuple, list[dict]] = {}
    for r in classified:
        grouped.setdefault((r['kind'], r['name'], r['namespace']), []).append(r)
    conflicts = []
    for (kind, name, namespace), items in grouped.items():
        selected = [x for x in items if x['selection_status'] == 'SELECTED_BY_SOURCE']
        if len(selected) > 1:
            conflicts.append({'kind': kind, 'name': name, 'namespace': namespace, 'status': 'MULTIPLE_SELECTED_DEFINITIONS', 'candidates': selected})
        elif len(items) > 1 and not selected:
            conflicts.append({'kind': kind, 'name': name, 'namespace': namespace, 'status': 'UNRESOLVED_MULTIPLE_CANDIDATES', 'candidates': items})
    return {'deployment_selection': classified, 'deployment_entrypoints': selections.get('entrypoints', []), 'deployment_selection_conflicts': conflicts, 'deployment_selection_warnings': selections.get('warnings', []), 'runtime_verified': False}



def discover_deployment_evidence(repo_root: Path, selections: dict) -> dict[str, Any]:
    """Inventory deployment-related repository evidence without asserting selection.

    Documentation references are informational only, never selection evidence.
    """
    root = Path(repo_root).resolve()
    selected_files = {
        item for entry in selections.get('entrypoints', [])
        for item in entry.get('selected_files', [])
    }
    inventory: list[dict[str, Any]] = []
    documentation: list[dict[str, Any]] = []
    for file in _source_files(root):
        rel = _rel(root, file)
        name = file.name
        lower = name.lower()
        kind = None
        if name in KUSTOMIZE:
            kind = 'kustomize_configuration'
        elif name == 'Chart.yaml':
            kind = 'helm_chart'
        elif lower.startswith('values') and file.suffix.lower() in {'.yaml', '.yml'}:
            kind = 'helm_values'
        elif (name in WORKFLOWS or rel.startswith('.github/workflows/')
              or lower.startswith('jenkinsfile')):
            kind = 'ci_cd_configuration'
        elif file.suffix.lower() in {'.yaml', '.yml'}:
            if any(d.get('kind') in {'Application', 'ApplicationSet'}
                   and str(d.get('apiVersion', '')).startswith('argoproj.io/')
                   for d in _yaml(file)):
                kind = 'argocd_configuration'
        if kind:
            inventory.append({
                'source_file': rel,
                'evidence_type': kind,
                'referenced_by_entrypoint': any(
                    entry.get('source_file') == rel for entry in selections.get('entrypoints', [])
                ),
                'selected_manifest_file': rel in selected_files,
                'runtime_verified': False,
            })
        if lower in {'readme.md', 'readme.rst', 'readme.txt', 'deploy.md',
                     'deployment.md', 'deployments.md'} or (
                file.suffix.lower() == '.md' and 'deploy' in lower):
            try:
                # Documentation may be huge; only inspect a bounded prefix.
                content = file.read_text(encoding='utf-8')[:200_000]
            except (OSError, UnicodeError):
                continue
            for line_number, line in enumerate(content.splitlines(), 1):
                if re.search(r'\b(?:kubectl\s+(?:apply|replace|create)|'
                             r'kubectl\s+kustomize|helm\s+(?:upgrade|install)|'
                             r'argocd\s+app|kustomize\s+build)\b', line, re.I):
                    documentation.append({
                        'source_file': rel, 'line': line_number,
                        'evidence': line.strip()[:300],
                        'classification': 'DOCUMENTATION_ONLY',
                    })
                    if len(documentation) >= 100:
                        break
    return {
        'deployment_evidence_inventory': inventory,
        'deployment_documentation_references': documentation,
        'deployment_evidence_summary': {
            'configuration_files_found': len(inventory),
            'documentation_references_found': len(documentation),
            'deployment_entrypoints_found': len(selections.get('entrypoints', [])),
            'selected_manifest_files': len(selected_files),
            'selection_verified_in_cluster': False,
        },
    }



def _safe_yaml_map(path: Path) -> dict[str, Any]:
    docs = _yaml(path)
    return docs[0] if docs else {}


def _kustomize_source_map(root: Path) -> list[dict[str, Any]]:
    """Resolve declared local source references, not rendered effective resources."""
    results: list[dict[str, Any]] = []
    for config in _source_files(root):
        if config.name not in KUSTOMIZE:
            continue
        directory = config.parent
        doc = _safe_yaml_map(config)
        refs: list[dict[str, Any]] = []
        warnings: list[str] = []
        for field in ('resources', 'bases', 'components'):
            values = doc.get(field) or []
            if not isinstance(values, list):
                warnings.append(f'{field} is not a list')
                continue
            for value in values:
                if not isinstance(value, str):
                    warnings.append(f'Non-string {field} reference')
                    continue
                target = _path(root, directory, value)
                status = 'UNRESOLVED'
                resolved = None
                if target is not None and target.exists():
                    resolved = _rel(root, target)
                    status = 'LOCAL_DIRECTORY' if target.is_dir() else 'LOCAL_FILE'
                refs.append({'field': field, 'reference': value, 'resolved_path': resolved, 'status': status})
                if status == 'UNRESOLVED':
                    warnings.append(f'Unresolved {field}: {value}')
        for field in ('patches', 'patchesStrategicMerge', 'patchesJson6902', 'images',
                      'configMapGenerator', 'secretGenerator', 'helmCharts',
                      'generators', 'transformers', 'replacements'):
            if doc.get(field):
                warnings.append(f'{field} affects effective output; rendering not performed')
        selected, traversal_warnings = _resolve_kustomize(root, directory)
        warnings.extend(traversal_warnings)
        results.append({
            'source_file': _rel(root, config),
            'environment_hint': directory.name if directory.parent.name in {'overlays', 'environments', 'envs'} else None,
            'references': refs,
            'declared_manifest_files': sorted(selected),
            'warnings': sorted(set(warnings)),
            'selection_status': 'DECLARED_IN_KUSTOMIZE',
            'runtime_verified': False,
        })
    return results


def _helm_source_map(root: Path) -> list[dict[str, Any]]:
    """Inventory chart templates/values without interpreting Helm Go templates."""
    charts: list[dict[str, Any]] = []
    for chart in _source_files(root):
        if chart.name != 'Chart.yaml':
            continue
        directory = chart.parent
        metadata = _safe_yaml_map(chart)
        values = sorted(_rel(root, p) for p in directory.glob('values*.yaml') if p.is_file())
        values += sorted(_rel(root, p) for p in directory.glob('values*.yml') if p.is_file())
        templates = sorted(_rel(root, p) for p in (directory / 'templates').rglob('*')
                           if p.is_file() and not any(part in SKIP for part in p.relative_to(root).parts)) if (directory / 'templates').is_dir() else []
        charts.append({
            'source_file': _rel(root, chart),
            'chart_name': metadata.get('name'),
            'chart_version': metadata.get('version'),
            'app_version': metadata.get('appVersion'),
            'dependencies': metadata.get('dependencies') if isinstance(metadata.get('dependencies'), list) else [],
            'values_files': sorted(set(values)),
            'template_files': templates,
            'rendered_resources': None,
            'warnings': ['Helm templates, values precedence, dependencies and generated manifests not evaluated'],
            'runtime_verified': False,
        })
    return charts


def _argocd_source_map(root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for file in _source_files(root):
        if file.suffix.lower() not in {'.yaml', '.yml'}:
            continue
        for index, doc in enumerate(_yaml(file), 1):
            if not str(doc.get('apiVersion', '')).startswith('argoproj.io/') or doc.get('kind') not in {'Application', 'ApplicationSet'}:
                continue
            spec = doc.get('spec') if isinstance(doc.get('spec'), dict) else {}
            sources = spec.get('sources') or ([spec['source']] if isinstance(spec.get('source'), dict) else [])
            declared = []
            for item in sources:
                if not isinstance(item, dict):
                    continue
                path = item.get('path')
                target = _path(root, root, path) if isinstance(path, str) else None
                local_path = _rel(root, target) if target and target.exists() else None
                helm = item.get('helm') if isinstance(item.get('helm'), dict) else {}
                declared.append({
                    'repo_url': item.get('repoURL'), 'target_revision': item.get('targetRevision'),
                    'path': path, 'chart': item.get('chart'),
                    'local_path_candidate': local_path,
                    'helm_value_files': helm.get('valueFiles') or [],
                    'helm_parameters': helm.get('parameters') or [],
                    'source_type_hint': 'helm' if item.get('chart') or helm or (target and (target / 'Chart.yaml').is_file()) else ('kustomize' if target and target.is_dir() and any((target / n).is_file() for n in KUSTOMIZE) else 'directory_or_unknown'),
                    'source_repository_verified': False,
                })
            results.append({
                'source_file': _rel(root, file), 'document_index': index,
                'kind': doc.get('kind'), 'name': (doc.get('metadata') or {}).get('name'),
                'sources': declared,
                'warnings': ['Source repository/revision and effective manifests not verified'] if doc.get('kind') == 'Application' else ['ApplicationSet generators/templates not expanded'],
                'runtime_verified': False,
            })
    return results


def discover_deployment_source_mapping(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    kustomize = _kustomize_source_map(root)
    helm = _helm_source_map(root)
    argocd = _argocd_source_map(root)
    return {
        'deployment_kustomize_source_map': kustomize,
        'deployment_helm_source_map': helm,
        'deployment_argocd_source_map': argocd,
        'deployment_source_mapping_summary': {
            'kustomize_configurations': len(kustomize),
            'helm_charts': len(helm),
            'argocd_declarations': len(argocd),
            'effective_manifests_rendered': False,
            'runtime_verified': False,
        },
    }

def analyze_deployment_selection(repo_root: Path, resources: list[dict]) -> dict:
    entries = discover_deployment_entrypoints(repo_root)
    selections = resolve_selected_manifests(repo_root, entries)
    report = build_deployment_selection_report(resources, selections)
    report.update(discover_deployment_evidence(repo_root, selections))
    report.update(discover_deployment_source_mapping(repo_root))
    return report
