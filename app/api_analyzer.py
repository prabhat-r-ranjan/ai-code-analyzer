
import re
from pathlib import Path


HTTP_ANNOTATIONS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": "ANY",
}


def extract_path(annotation: str) -> str:
    match = re.search(
        r'(?:value\s*=\s*|path\s*=\s*)?"([^"]+)"',
        annotation,
    )
    return match.group(1) if match else ""


def join_paths(base: str, path: str) -> str:
    combined = "/".join(
        part.strip("/")
        for part in [base, path]
        if part and part.strip("/")
    )
    return "/" + combined if combined else "/"



def analyze_apis(repo_root: Path) -> list[dict]:
    endpoints = []

    annotation_pattern = re.compile(
        r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|"
        r"PatchMapping|RequestMapping)\s*"
        r"(\([^)]*\))?",
        re.DOTALL,
    )

    class_pattern = re.compile(
        r"\bclass\s+(\w+)"
    )

    for java_file in repo_root.rglob("*.java"):
        if ".git" in java_file.parts:
            continue

        source = java_file.read_text(
            encoding="utf-8",
            errors="replace"
        )

        if "@RestController" not in source:
            continue

        class_match = class_pattern.search(source)
        if not class_match:
            continue

        controller = class_match.group(1)

        # Read annotations before class declaration
        class_header = source[:class_match.start()]

        class_mappings = list(
            annotation_pattern.finditer(class_header)
        )

        base_path = ""

        for mapping in class_mappings:
            if mapping.group(1) == "RequestMapping":
                base_path = extract_path(
                    mapping.group(2) or ""
                )

        # Only process method-level mappings
        for match in annotation_pattern.finditer(
            source, class_match.end()
        ):
            annotation = match.group(1)
            args = match.group(2) or ""

            method = HTTP_ANNOTATIONS[annotation]
            path = extract_path(args)

            endpoints.append({
                "controller": controller,
                "http_method": method,
                "endpoint": join_paths(
                    base_path, path
                ),
                "source_file": str(
                    java_file.relative_to(repo_root)
                ).replace("\\", "/"),
            })

    return endpoints
