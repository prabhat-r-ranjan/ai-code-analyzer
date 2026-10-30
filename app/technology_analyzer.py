
from pathlib import Path
import xml.etree.ElementTree as ET


def analyze_technologies(pom_path: Path) -> dict:
    tree = ET.parse(pom_path)
    root = tree.getroot()

    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}

    def find_text(path):
        element = root.find(path, namespace)
        return element.text.strip() if element is not None and element.text else None

    java_version = (
        find_text("m:properties/m:java.version")
        or find_text("m:properties/m:maven.compiler.release")
        or find_text("m:properties/m:maven.compiler.target")
    )

    spring_boot_version = None
    parent_artifact = find_text("m:parent/m:artifactId")

    if parent_artifact == "spring-boot-starter-parent":
        spring_boot_version = find_text("m:parent/m:version")

    dependencies = []

    for dep in root.findall("m:dependencies/m:dependency", namespace):
        group = dep.findtext("m:groupId", namespaces=namespace)
        artifact = dep.findtext("m:artifactId", namespaces=namespace)
        version = dep.findtext("m:version", namespaces=namespace)

        dependencies.append({
            "group_id": group,
            "artifact_id": artifact,
            "version": version,
        })

    return {
        "artifact_id": find_text("m:artifactId"),
        "java_version": java_version,
        "spring_boot_version": spring_boot_version,
        "build_tool": "Maven",
        "dependencies": dependencies,
        "dependency_count": len(dependencies),
    }
