
from pathlib import Path
import re


def analyze_downstream(repo_root: Path) -> list[dict]:
    findings = []
    seen = set()

    patterns = {
        "RestTemplate": r"\bRestTemplate\b",
        "WebClient": r"\bWebClient\b",
        "OpenFeign": r"@FeignClient\s*\(",
        "Java HttpClient": r"\bHttpClient\b",
    }

    for file in repo_root.rglob("*.java"):
        if ".git" in file.parts:
            continue

        try:
            content = file.read_text(
                encoding="utf-8",
                errors="replace"
            )
        except OSError:
            continue

        source_file = file.relative_to(
            repo_root
        ).as_posix()

        for technology, pattern in patterns.items():
            if not re.search(pattern, content):
                continue

            key = (source_file, technology)
            if key in seen:
                continue

            seen.add(key)

            findings.append({
                "type": "HTTP Client",
                "technology": technology,
                "direction": "outbound_candidate",
                "target_service": None,
                "endpoint": None,
                "source_file": source_file,
                "status": "requires_code_review"
            })

    return findings
