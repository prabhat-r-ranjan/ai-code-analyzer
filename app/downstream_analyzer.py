"""Conservative outbound HTTP call evidence from Java source.

Does not infer a downstream service from an import, bean, or dependency alone.
Never reads or exports credential values or HTTP request arguments.
"""
from pathlib import Path
import re

MAX_BYTES = 1024 * 1024
EXCLUDED = {'.git', 'target', 'build', '.gradle'}
CALLS = {
    'RestTemplate': re.compile(r'\b(\w+)\s*\.\s*(exchange|getForObject|getForEntity|postForObject|postForEntity|postForLocation|put|delete|patchForObject|execute)\s*\('),
    'WebClient': re.compile(r'\b(\w+)\s*\.\s*(get|post|put|patch|delete|method)\s*\('),
    'Java HttpClient': re.compile(r'\b(\w+)\s*\.\s*(send|sendAsync)\s*\('),
}
TYPES = {
    'RestTemplate': re.compile(r'\bRestTemplate\s+(\w+)\b'),
    'WebClient': re.compile(r'\bWebClient\s+(\w+)\b'),
    'Java HttpClient': re.compile(r'\bHttpClient\s+(\w+)\b'),
}
FEIGN = re.compile(r'@FeignClient\s*\(')


def analyze_downstream(repo_root: Path) -> list[dict]:
    findings = []
    seen = set()
    for file in sorted(repo_root.rglob('*.java')):
        if any(part in EXCLUDED for part in file.relative_to(repo_root).parts) or file.is_symlink():
            continue
        try:
            if file.stat().st_size > MAX_BYTES:
                continue
            content = file.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        source_file = file.relative_to(repo_root).as_posix()
        for technology, pattern in CALLS.items():
            variables = set(TYPES[technology].findall(content))
            for match in pattern.finditer(content):
                variable, operation = match.groups()
                if variable not in variables:
                    continue
                key = (source_file, technology, variable, operation)
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    'type': 'HTTP Client', 'technology': technology,
                    'direction': 'outbound_candidate',
                    'target_service': None, 'endpoint': None,
                    'source_file': source_file,
                    'operation': operation,
                    'status': 'source_call_detected_target_unresolved',
                    'runtime_verified': False,
                })
        # Feign declaration proves a configured HTTP-client interface candidate,
        # not a network request or resolved target.
        if FEIGN.search(content):
            key = (source_file, 'OpenFeign')
            if key not in seen:
                seen.add(key)
                findings.append({
                    'type': 'HTTP Client', 'technology': 'OpenFeign',
                    'direction': 'outbound_candidate',
                    'target_service': None, 'endpoint': None,
                    'source_file': source_file,
                    'status': 'client_declaration_target_unresolved',
                    'runtime_verified': False,
                })
    return findings
