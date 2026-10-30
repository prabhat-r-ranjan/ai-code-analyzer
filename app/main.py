
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.repository import analyze_repository
from fastapi.responses import StreamingResponse
from app.excel_generator import generate_excel
from app.dependency_correlator import correlate_dependencies
from app.application_dependency_analyzer import (
    correlate_application_dependencies,
)

app = FastAPI(title="AI Code Analyzer")


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: str | None = None


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    try:
        result = analyze_repository(
            repo_url=request.repo_url,
            branch=request.branch,
        )

        # Milestone 12: Kubernetes dependency correlation
        deployment_details = result.get(
            "deployment_details", []
        )

        correlation = correlate_dependencies(
            deployment_details
        )

        result.update(correlation)

        # Milestone 13: Application-to-database correlation
        result["application_dependencies"] = (
            correlate_application_dependencies(
                result.get("database_details", []),
                deployment_details,
            )
        )

        return result

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


@app.post("/analyze/excel")
def analyze_excel(request: AnalyzeRequest):
    try:
        analysis = analyze_repository(
            repo_url=request.repo_url,
            branch=request.branch,
        )

        # Milestone 12: Kubernetes dependency correlation
        deployment_details = analysis.get(
            "deployment_details", []
        )

        correlation = correlate_dependencies(
            deployment_details
        )

        analysis.update(correlation)

        # Milestone 13: Application-to-database correlation
        analysis["application_dependencies"] = (
            correlate_application_dependencies(
                analysis.get("database_details", []),
                deployment_details,
            )
        )

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
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Excel generation failed. Check server logs.",
        )
