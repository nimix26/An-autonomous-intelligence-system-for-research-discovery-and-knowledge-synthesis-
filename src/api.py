"""
FastAPI Backend — POST /analyze endpoint
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SynthScholar API",
    description="Context-aware research summarization pipeline",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()


class AnalyzeRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500)
    persona: str = Field(default="Learner")
    depth: str = Field(default="Understand")
    knowledge_level: str = Field(default="Intermediate")
    time_budget: str = Field(default="Focused")
    goal: str = Field(default="Learn")
    output_format: str = Field(default="Structured")

    def validate_and_normalize(self) -> dict:
        PERSONAS = {"Learner", "Educator", "Researcher"}
        DEPTHS = {"Skim", "Understand", "DeepDive"}
        KNOWLEDGE = {"Beginner", "Intermediate", "Advanced"}
        TIME_BUDGETS = {"Quick", "Focused", "DeepResearch"}
        GOALS = {"Learn", "Teach", "Publish"}
        FORMATS = {"Bullet", "Structured", "Report"}

        return {
            "topic": self.topic.strip(),
            "persona": self.persona if self.persona in PERSONAS else "Learner",
            "depth": self.depth if self.depth in DEPTHS else "Understand",
            "knowledge_level": self.knowledge_level if self.knowledge_level in KNOWLEDGE else "Intermediate",
            "time_budget": self.time_budget if self.time_budget in TIME_BUDGETS else "Focused",
            "goal": self.goal if self.goal in GOALS else "Learn",
            "output_format": self.output_format if self.output_format in FORMATS else "Structured",
        }


class PaperMeta(BaseModel):
    title: str
    authors: list[str] = []
    year: Optional[int] = None
    source: str = ""
    citation_count: Optional[int] = None


class AnalyzeResponse(BaseModel):
    summary: str
    key_insights: list[str] = []
    gaps: list[str] = []
    ideas: list[str] = []
    papers_found: int = 0
    analysis_mode: str = "abstract_based"
    papers_metadata: list[PaperMeta] = []
    visible_tabs: list[str] = ["summary", "insights", "papers"]


@app.get("/")
async def root():
    return {"service": "SynthScholar", "status": "running", "version": "2.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    normalized = request.validate_and_normalize()
    logger.info(
        f"[API] Analyze: topic='{normalized['topic']}', "
        f"persona={normalized['persona']}, depth={normalized['depth']}, "
        f"goal={normalized['goal']}"
    )

    try:
        result = await orchestrator.run_pipeline(normalized)
        return AnalyzeResponse(**result)
    except Exception as e:
        logger.error(f"[API] Pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)