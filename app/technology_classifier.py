
TECHNOLOGY_RULES = {
    "spring-boot-starter-web": ("REST Communication", "Spring Web"),
    "spring-boot-starter-data-jpa": ("ORM", "Spring Data JPA"),
    "postgresql": ("Database Driver", "PostgreSQL"),
    "mssql-jdbc": ("Database Driver", "Microsoft SQL Server"),
    "spring-boot-starter-validation": ("Validation", "Spring Validation"),
    "spring-boot-starter-actuator": ("Monitoring", "Spring Boot Actuator"),
    "micrometer-registry-prometheus": ("Metrics", "Micrometer Prometheus"),
    "spring-boot-starter-test": ("Unit Testing", "Spring Boot Test"),
    "lombok": ("Code Generation", "Lombok"),
    "spring-kafka": ("Event Streaming", "Apache Kafka"),
    "liquibase-core": ("Database Migration", "Liquibase"),
    "spring-boot-starter-oauth2-client": ("Security", "OAuth2 Client"),
    "spring-boot-starter-oauth2-resource-server": (
        "Security", "OAuth2 Resource Server"
    ),
}


def classify_technologies(analysis: dict) -> list[dict]:
    technologies = [
        {
            "category": "Language",
            "technology": f"Java {analysis['java_version']}"
            if analysis.get("java_version") else "Java (version unknown)",
            "evidence": analysis["pom_file"],
        },
        {
            "category": "Framework",
            "technology": f"Spring Boot {analysis['spring_boot_version']}"
            if analysis.get("spring_boot_version") else "Not detected",
            "evidence": analysis["pom_file"],
        },
        {
            "category": "Build Tool",
            "technology": analysis["build_tool"],
            "evidence": analysis["pom_file"],
        },
    ]

    seen = set()

    for dependency in analysis.get("dependencies", []):
        artifact = dependency.get("artifact_id")

        if artifact not in TECHNOLOGY_RULES:
            continue

        category, technology = TECHNOLOGY_RULES[artifact]
        key = (category, technology)

        if key in seen:
            continue

        seen.add(key)

        technologies.append({
            "category": category,
            "technology": technology,
            "evidence": (
                f"{analysis['pom_file']} "
                f"({dependency.get('group_id')}:{artifact})"
            ),
        })

    return technologies
