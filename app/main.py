from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator
from fastapi.responses import StreamingResponse

from app.repository import analyze_repository
from app.excel_generator import generate_excel
from app.dependency_correlator import correlate_dependencies
from app.migration_impact_analyzer import analyze_migration_impact
from app.runtime_cluster_analyzer import collect_runtime_snapshot
from app.application_dependency_analyzer import (
    correlate_application_dependencies,
    correlate_application_configuration,
    correlate_end_to_end_dependencies,
)

app = FastAPI(title="AI Code Analyzer")


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: str | None = None
    include_runtime: bool = False
    runtime_context: str | None = None
    runtime_namespace: str | None = None
    runtime_kubeconfig: str | None = None

    @model_validator(mode="after")
    def validate_runtime_options(self):
        if self.include_runtime:
            if not self.runtime_context or not self.runtime_context.strip():
                raise ValueError("runtime_context is required when include_runtime=true")
            if (not self.runtime_namespace or not self.runtime_namespace.strip()
                    or self.runtime_namespace.strip() == "*"):
                raise ValueError("An explicit runtime_namespace is required when include_runtime=true")
        return self


@app.get("/health")
def health():
    return {"status": "UP"}


def run_full_assessment(
    repo_url: str,
    branch: str | None = None,
    *,
    include_runtime: bool = False,
    runtime_context: str | None = None,
    runtime_namespace: str | None = None,
    runtime_kubeconfig: str | None = None,
):
    # Existing source assessment pipeline remains unchanged.
    result = analyze_repository(repo_url=repo_url, branch=branch)
    deployment_details = result.get("deployment_details", [])

    result.update(correlate_dependencies(deployment_details))
    result["application_dependencies"] = correlate_application_dependencies(
        result.get("database_details", []), deployment_details
    )
    result["application_configuration_dependencies"] = (
        correlate_application_configuration(deployment_details)
    )
    result["end_to_end_dependencies"] = correlate_end_to_end_dependencies(
        result.get("database_details", []), deployment_details
    )
    result.update(analyze_migration_impact(result))

    # Runtime evidence is independent of the source analysis.
    # No source-to-runtime provenance is asserted.
    if include_runtime:
        if not runtime_context or not runtime_namespace or runtime_namespace == "*":
            raise ValueError("Explicit runtime_context and runtime_namespace are required")
        try:
            snapshot = collect_runtime_snapshot(
                context=runtime_context,
                namespace=runtime_namespace,
                kubeconfig=runtime_kubeconfig,
            )
        except ValueError:
            raise
        except Exception as exc:
            # Do not return kubeconfig paths or API details to the HTTP client.
            raise RuntimeError("Runtime collection failed; check server logs") from exc

        result["runtime_assessment"] = snapshot
        result["runtime_assessment_note"] = (
            "Independent namespace runtime inventory. Not proof that the assessed "
            "repository produced these resources. No source-to-runtime correlation performed."
        )
    return result


def _assess(request: AnalyzeRequest):
    return run_full_assessment(
        repo_url=request.repo_url,
        branch=request.branch,
        include_runtime=request.include_runtime,
        runtime_context=request.runtime_context,
        runtime_namespace=request.runtime_namespace,
        runtime_kubeconfig=request.runtime_kubeconfig,
    )


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    try:
        return _assess(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Repository analysis failed. Check server logs.",
        ) from exc


@app.post("/analyze/excel")
def analyze_excel(request: AnalyzeRequest):
    try:
        analysis = _assess(request)
        excel_file = generate_excel(analysis)
        return StreamingResponse(
            excel_file,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": 'attachment; filename="migration-assessment.xlsx"'
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Excel generation failed. Check server logs.",
        ) from exc
