
from pathlib import Path
from urllib.parse import urlsplit
import re
import yaml


def flatten_config(data, prefix=""):
    result = {}

    if not isinstance(data, dict):
        return result

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)

        if isinstance(value, dict):
            result.update(flatten_config(value, full_key))
        else:
            result[full_key] = value

    return result


def parse_properties(content):
    result = {}

    for line in content.splitlines():
        line = line.strip()

        if not line or line.startswith(("#", "!")):
            continue

        match = re.match(r"([^=:]+)\s*[=:]\s*(.*)", line)

        if match:
            result[match.group(1).strip()] = match.group(2).strip()

    return result


def parse_jdbc_url(url):
    if not isinstance(url, str):
        return {}

    # Don't export URLs with embedded credentials.
    if "${" in url:
        return {"jdbc_url": "Environment variable / placeholder"}

    match = re.match(r"jdbc:([^:]+):", url)
    if not match:
        return {}

    db_type = match.group(1).lower()

    result = {"database_type": db_type}

    if db_type == "sqlserver":
        match = re.match(
            r"jdbc:sqlserver://([^;]+)(?:;(.*))?", url
        )
        if match:
            host_port = match.group(1)
            properties = match.group(2) or ""
            host, _, port = host_port.partition(":")

            result["host"] = host
            result["port"] = port or "1433"

            db_match = re.search(
                r"databaseName=([^;]+)",
                properties,
                re.IGNORECASE
            )
            if db_match:
                result["database_name"] = db_match.group(1)

    elif db_type in ("postgresql", "mysql", "mariadb"):
        parsed = urlsplit(url.removeprefix("jdbc:"))

        result["host"] = parsed.hostname
        result["port"] = parsed.port
        result["database_name"] = parsed.path.lstrip("/")

    return result


def analyze_databases(repo_root: Path):
    findings = []

    patterns = (
        "application.yml",
        "application.yaml",
        "application.properties",
        "application-*.yml",
        "application-*.yaml",
        "application-*.properties",
    )

    files = set()

    for pattern in patterns:
        files.update(repo_root.rglob(pattern))

    for file in sorted(files):
        if ".git" in file.parts:
            continue

        try:
            content = file.read_text(
                encoding="utf-8",
                errors="replace"
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

        for config in configs:
            url = config.get("spring.datasource.url")

            if not url:
                continue

            finding = {
                "source_file": str(
                    file.relative_to(repo_root)
                ).replace("\\", "/"),
                "datasource": "spring.datasource",
                "status": "configured",
            }

            finding.update(parse_jdbc_url(url))

            if "${" in str(url):
                finding["status"] = "requires_runtime_resolution"

            dialect = config.get(
                "spring.jpa.database-platform"
            )

            if dialect and "${" not in str(dialect):
                finding["jpa_dialect"] = dialect

            findings.append(finding)

    return findings
