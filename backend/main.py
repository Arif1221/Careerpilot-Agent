import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import CareerPilotAgent

app = FastAPI(
    title="CareerPilot AI Agent",
    description="Autonomous ATS resume-scoring agent (Parse -> Match -> Generate -> Self-review).",
    version="1.0.0",
)

allowed_origins = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = CareerPilotAgent()


class AnalyzeRequest(BaseModel):
    resume_text: str = Field(..., min_length=20, description="Plain text of the resume")
    job_description: str = Field(..., min_length=20, description="Plain text of the target JD")


class RewrittenBullet(BaseModel):
    original: str
    improved: str


class AnalyzeResponse(BaseModel):
    match_score: int
    matched_must_have: list[str]
    missing_must_have: list[str]
    matched_nice_to_have: list[str]
    missing_nice_to_have: list[str]
    missing_sections: list[str]
    suggestions: list[str]
    rewritten_bullets: list[RewrittenBullet]
    reviewer_notes: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    try:
        result = agent.run(req.resume_text, req.job_description)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the client
        raise HTTPException(status_code=500, detail=f"Agent run failed: {exc}") from exc
    return result.to_dict()
