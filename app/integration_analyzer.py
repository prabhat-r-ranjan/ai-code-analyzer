
from pathlib import Path
import re

import yaml

from app.database_analyzer import flatten_config, parse_properties


def analyze_integrations(repo_root: Path) -> list[dict]:
    findings = []
    seen = set()

    def add_finding(kind, name, source_file, evidence):
        key = (kind, name, source_file, evidence)

        if key in seen:
            return

        seen.add(key)
        findings.append({
            "type": kind,
            "name": name,
            "source_file": source_file,
            "evidence": evidence,
            "status": "detected",
        })

    # 1. Scan Java code for integration annotations/classes
    java_patterns = {
        "Kafka": [
            r"@KafkaListener\b",
            r"\bKafkaTemplate\b",
            r"\bConsumerRecord\b",
        ],
        "OAuth2": [
            r"\bOAuth2AuthorizedClient\b",
            r"\bJwtDecoder\b",
            r"\bJwtAuthenticationToken\b",
        ],
    }

    for file in repo_root.rglob("*.java"):
        if ".git" in file.parts:
            continue

        source = file.read_text(
            encoding="utf-8",
            errors="replace",
        )
        relative = file.relative_to(repo_root).as_posix()

        for name, patterns in java_patterns.items():
            for pattern in patterns:
                if re.search(pattern, source):
                    add_finding(
                        "integration",
                        name,
                        relative,
                        pattern,
                    )

    # 2. Scan Spring configuration
    config_patterns = [
        "application.yml",
        "application.yaml",
        "application.properties",
        "application-*.yml",
        "application-*.yaml",
        "application-*.properties",
    ]

    config_files = set()
    for pattern in config_patterns:
        config_files.update(repo_root.rglob(pattern))

    for file in sorted(config_files):
        if ".git" in file.parts:
            continue

        try:
            content = file.read_text(
                encoding="utf-8",
                errors="replace",
            )

            if file.suffix in (".yml", ".yaml"):
                configs = [
                    flatten_config(doc)
                    for doc in yaml.safe_load_all(content)
                    if isinstance(doc, dict)
                ]
            else:
                configs = [parse_properties(content)]

        except (OSError, yaml.YAMLError, ValueError):
            continue

        relative = file.relative_to(repo_root).as_posix()

        for config in configs:
            for key in config:
                normalized = key.lower()

                if normalized.startswith("spring.kafka."):
                    add_finding(
                        "configuration",
                        "Kafka",
                        relative,
                        key,
                    )

                if normalized.startswith(
                    "spring.security.oauth2."
                ):
                    add_finding(
                        "configuration",
                        "OAuth2",
                        relative,
                        key,
                    )

    return findings
