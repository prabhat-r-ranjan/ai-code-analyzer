"""Conservative static Java outbound-client evidence; never emits credential values.

Evidence is a candidate, not a verified network call. No Java AST or runtime tracing.
"""
from pathlib import Path
import re

CLIENT_TYPE = re.compile(r"\b(?:private|protected|public)\s+(?:final\s+)?([A-Z][\w]*(?:Api|Client))\s+(\w+)\s*;")
CONFIG_PROPERTY = re.compile(r'@ConfigurationProperties\s*\(\s*(?:prefix\s*=\s*)?["\']([^"\']+)["\']\s*\)')
BASE_PATH = re.compile(r'\b(?:setBasePath|baseUrl|baseUri)\s*\(\s*([^;\n]+?)\s*\)')
PROPERTY_GETTER = re.compile(r'\b\w+\.(get[A-Z]\w*)\s*\(\s*\)')
PROPERTY_DECL = re.compile(r'\b(?:private|protected)\s+(?:String|URI|URL)\s+(\w+)\s*;')
ENV_REF = re.compile(r'\$\{([A-Za-z_][A-Za-z_0-9]*)(?::[^}]*)?\}')
SAFE_EXTENSIONS = {'.yml', '.yaml', '.properties'}
MAX_FILE_SIZE = 1024 * 1024


def _read(path):
    try:
        if path.stat().st_size > MAX_FILE_SIZE or path.is_symlink():
            return None
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def _java_files(root):
    for path in sorted(root.rglob('*.java')):
        if any(p in {'.git', 'target', 'build', '.gradle'} for p in path.relative_to(root).parts):
            continue
        yield path


def _config_inventory(root):
    """Capture only property names and environment variable names, not values."""
    names = set()
    env_names = set()
    for path in root.rglob('*'):
        if path.suffix.lower() not in SAFE_EXTENSIONS or not path.is_file():
            continue
        if any(p in {'.git', 'target', 'build'} for p in path.relative_to(root).parts):
            continue
        content = _read(path)
        if content is None:
            continue
        env_names.update(ENV_REF.findall(content))
        if path.suffix == '.properties':
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith(('#', '!')):
                    match = re.match(r'([\w.\-]+)\s*[:=]', line)
                    if match:
                        names.add(match.group(1))
    return names, env_names


def analyze_source_clients(root: Path) -> list[dict]:
    """Find typed API client field invocations and candidate base-path wiring."""
    files = {}
    for path in _java_files(root):
        content = _read(path)
        if content is not None:
            files[str(path.relative_to(root))] = content

    property_prefixes = []
    property_fields = set()
    base_path_wiring = []
    for file, content in files.items():
        for prefix in CONFIG_PROPERTY.findall(content):
            property_prefixes.append({'prefix': prefix, 'source_file': file})
            property_fields.update(PROPERTY_DECL.findall(content))
        for match in BASE_PATH.finditer(content):
            expr = match.group(1).strip()
            getters = PROPERTY_GETTER.findall(expr)
            for getter in getters:
                property_name = getter[3:4].lower() + getter[4:]
                base_path_wiring.append({
                    'source_file': file,
                    'property_field': property_name,
                    'configuration_expression': 'property_getter',
                })

    property_keys, environment_names = _config_inventory(root)
    evidence = []
    seen = set()
    for file, content in files.items():
        for declaration in CLIENT_TYPE.finditer(content):
            client_type, variable = declaration.groups()
            # Match method invocation on the declared variable; do not count constructor/config-only references.
            invocation = re.compile(r'\b' + re.escape(variable) + r'\s*\.\s*([A-Za-z_]\w*)\s*\(')
            for call in invocation.finditer(content):
                method = call.group(1)
                if method in {'toString', 'hashCode', 'equals'}:
                    continue
                key = (file, client_type, variable, method)
                if key in seen:
                    continue
                seen.add(key)
                # Configuration may belong to a different bean; do not assert a binding without a trace.
                evidence.append({
                    'relationship': 'candidate_outbound_api_client_call',
                    'source_file': file,
                    'line': content.count('\n', 0, call.start()) + 1,
                    'client_type': client_type,
                    'client_variable': variable,
                    'operation': method,
                    'base_path_wiring_candidates': base_path_wiring,
                    'configuration_prefix_candidates': property_prefixes,
                    'configuration_property_keys_detected': sorted(property_keys),
                    'environment_variable_names_detected': sorted(environment_names),
                    'resolution': 'source_call_detected_configuration_binding_unverified',
                    'runtime_verified': False,
                    'validation_required': 'Verify injected client bean, effective profile, resolved URL, and outbound connectivity.',
                })
    return evidence
