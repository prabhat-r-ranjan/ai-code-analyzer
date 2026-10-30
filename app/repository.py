
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from app.technology_analyzer import analyze_technologies
from git import Repo
from app.technology_classifier import classify_technologies
from app.api_analyzer import analyze_apis
from app.database_analyzer import analyze_databases
from app.integration_analyzer import analyze_integrations
from app.downstream_analyzer import analyze_downstream

def analyze_repository(repo_url: str, branch: str | None = None) -> dict:
    parsed = urlparse(repo_url)

    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("A valid HTTPS repository URL is required")

    if parsed.username or parsed.password:
        raise ValueError("Do not include credentials in repository URLs")

    with TemporaryDirectory(prefix="migration-assessment-") as temp_dir:
        clone_options = {
            "url": repo_url,
            "to_path": temp_dir,
            "depth": 1,
            "multi_options": ["--no-tags"],
        }

        if branch:
            clone_options["branch"] = branch

        Repo.clone_from(**clone_options)

        root = Path(temp_dir)

        pom_files = [
            str(path.relative_to(root))
            for path in root.rglob("pom.xml")
            if ".git" not in path.parts
        ]
        technologies = []
        for pom_file in pom_files:
            pom_path = root / pom_file

            result = analyze_technologies(pom_path)
            result["pom_file"] = pom_file
            result["classified_technology"] = classify_technologies(result)
            technologies.append({
                "pom_file": pom_file,
                **result
            })
        api_endpoints = analyze_apis(root)
        database_details = analyze_databases(root)
        integration_details = analyze_integrations(root)
        downstream_details = analyze_downstream(root)
        return {
            "repository": repo_url,
            "branch": branch or "default",
            "pom_files": sorted(pom_files),
            "pom_count": len(pom_files),
            "status": "completed",
            "technologies": technologies,
            "api_endpoints": api_endpoints,
            "api_count": len(api_endpoints),
            "database_details": database_details,
            "database_count": len(database_details),
            "integration_details": integration_details,
            "integration_count": len(integration_details),
            "downstream_details": downstream_details,
            "downstream_count": len(downstream_details),
        }
