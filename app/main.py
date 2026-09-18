from fastapi import FastAPI

app = FastAPI(title="AI Code Analyzer")


@app.get("/health")
def health():
    return {
        "status": "UP"
    }


@app.post("/analyze")
def analyze():
    return {
        "status": "success",
        "message": "Code analyzer skeleton is working",
        "findings": []
    }