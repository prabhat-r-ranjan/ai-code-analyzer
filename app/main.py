
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.repository import analyze_repository
from fastapi.responses import StreamingResponse
from app.excel_generator import generate_excel


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