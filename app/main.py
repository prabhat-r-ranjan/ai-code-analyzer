
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from app.repository import analyze_repository
from app.excel_generator import generate_excel
from app.dependency_correlator import correlate_dependencies
from app.migration_impact_analyzer import analyze_migration_impact

from app.application_dependency_analyzer import (
    correlate_application_dependencies,
    correlate_application_configuration,
    correlate_end_to_end_dependencies,
)

app = FastAPI(title="AI Code Analyzer")


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: str | None = None


@app.get("/health")
def health():
    return {"status": "UP"}


# -------------------------------------------------
# COMMON ASSESSMENT PIPELINE
# Used by JSON and Excel endpoints
# -------------------------------------------------

def run_full_assessment(repo_url: str, branch: str | None = None):

    # Step 1: Repository discovery
    result = analyze_repository(
        repo_url=repo_url,
        branch=branch,
    )

    deployment_details = result.get("deployment_details", [])

    # Step 2: Kubernetes dependency correlation
    correlation = correlate_dependencies(deployment_details)
    result.update(correlation)

    # Step 3: Application-to-database dependencies
    result["application_dependencies"] = (
        correlate_application_dependencies(
            result.get("database_details", []),
            deployment_details,
        )
    )

    # Step 4: ConfigMap and Secret dependencies
    result["application_configuration_dependencies"] = (
        correlate_application_configuration(
            deployment_details
        )
    )

    # Step 5: End-to-end dependency chains
    result["end_to_end_dependencies"] = (
        correlate_end_to_end_dependencies(
            result.get("database_details", []),
            deployment_details,
        )
    )

    # Step 6: Migration impact and risk assessment
    migration_impact = analyze_migration_impact(result)
    result.update(migration_impact)

    return result


# -------------------------------------------------
# JSON ASSESSMENT
# -------------------------------------------------

@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    try:
        return run_full_assessment(
            repo_url=request.repo_url,
            branch=request.branch,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Repository analysis failed. Check server logs.",
        )


# -------------------------------------------------
# EXCEL ASSESSMENT
# -------------------------------------------------

@app.post("/analyze/excel")
def analyze_excel(request: AnalyzeRequest):
    try:
        # Same complete assessment as /analyze
        analysis = run_full_assessment(
            repo_url=request.repo_url,
            branch=request.branch,
        )

        # Generate Excel with all assessment results
        excel_file = generate_excel(analysis)

        return StreamingResponse(
            excel_file,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition":
                'attachment; filename="migration-assessment.xlsx"'
            },
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Excel generation failed. Check server logs.",
        )
